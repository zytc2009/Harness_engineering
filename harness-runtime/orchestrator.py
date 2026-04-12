"""
One-Shot Pipeline Orchestrator
================================
Each phase makes exactly ONE LLM call. No tool loops, no ReAct patterns.

Flow:
  architect   -> 1 call -> design.md written to sandbox
  implementer -> 1 call -> code files written to sandbox
  tester      -> 1 call (generates test_impl.py) + local execution -> pass/fail

  If tests fail -> retry implementer (with failure feedback) -> up to max_retries
"""

import os
import re
import subprocess
import sys
import tempfile
import logging
from collections.abc import Callable
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

import config
import execution
from prompts import get_system_prompt

SANDBOX = Path(tempfile.gettempdir()) / "harness_sandbox"
SANDBOX.mkdir(exist_ok=True)
logger = logging.getLogger(__name__)
_IMPLEMENTER_EMPTY_OUTPUT = (
    "Implementer produced no parseable `## FILE:` blocks. "
    "The response must contain machine-readable file blocks only."
)


def _resolve_sandbox_dir(sandbox_dir: str | Path | None = None) -> Path:
    path = Path(sandbox_dir) if sandbox_dir is not None else SANDBOX
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_files(text: str) -> dict[str, str]:
    """Parse structured file blocks from LLM output."""
    files = {}
    pattern = r"##\s*FILE:\s*(\S+)\s*\n```[^\n]*\n(.*?)```"
    for match in re.finditer(pattern, text, re.DOTALL):
        name = os.path.basename(match.group(1).strip())
        files[name] = match.group(2).rstrip()
    return files


def _write_sandbox(files: dict[str, str], sandbox_dir: str | Path | None = None) -> None:
    target_dir = _resolve_sandbox_dir(sandbox_dir)
    for name, content in files.items():
        (target_dir / name).write_text(content, encoding="utf-8")


def _read_sandbox(sandbox_dir: str | Path | None = None) -> dict[str, str]:
    result = {}
    target_dir = _resolve_sandbox_dir(sandbox_dir)
    for path in sorted(target_dir.iterdir()):
        if path.is_file():
            try:
                result[path.name] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Failed to read sandbox file %s: %s", path, exc)
    return result


def architect_phase(
    task: str,
    sandbox_dir: str | Path | None = None,
    task_metadata: dict | None = None,
) -> str:
    """One LLM call -> design.md in sandbox."""
    print("\n[HARNESS] Phase: architect")
    text = execution.invoke_phase("architect", [
        SystemMessage(content=get_system_prompt("architect", task_metadata=task_metadata)),
        HumanMessage(content=task),
    ], task_metadata=task_metadata)

    md = re.search(r"```(?:markdown|md)?\n(.*?)```", text, re.DOTALL)
    design = md.group(1).strip() if md else text

    _write_sandbox({"design.md": design}, sandbox_dir=sandbox_dir)
    print(f"  -> design.md written ({len(design)} chars)")
    return design


def implementer_phase(
    task: str,
    design: str,
    feedback: str = "",
    sandbox_dir: str | Path | None = None,
    task_metadata: dict | None = None,
) -> dict[str, str]:
    """One LLM call -> code files written to sandbox."""
    print("\n[HARNESS] Phase: implementer")

    prompt = f"Task: {task}\n\n## Design Document\n{design}"
    if feedback:
        prompt += f"\n\n## Test Failures to Fix\n{feedback}"

    text = execution.invoke_phase("implementer", [
        SystemMessage(content=get_system_prompt("implementer", task_metadata=task_metadata)),
        HumanMessage(content=prompt),
    ], task_metadata=task_metadata)

    files = _parse_files(text)
    if not files:
        print("  [HARNESS] Warning: no parseable ## FILE: blocks in implementer output.")
        print(f"  Response preview: {text[:300]}")
    else:
        _write_sandbox(files, sandbox_dir=sandbox_dir)
        for name in sorted(files):
            print(f"  -> {name} written ({len(files[name])} chars)")

    return files


_CPP_EXTS = {".cpp", ".cc", ".cxx", ".c", ".h", ".hpp"}
_SH_EXTS = {".sh", ".bash"}
_GO_EXTS = {".go"}
_PY_EXTS = {".py"}


def _detect_language(impl_files: dict[str, str]) -> str:
    """Infer primary implementation language from non-test file extensions."""
    counts: dict[str, int] = {}
    for name in impl_files:
        ext = Path(name).suffix.lower()
        counts[ext] = counts.get(ext, 0) + 1

    for ext in sorted(counts, key=lambda value: -counts[value]):
        if ext in _CPP_EXTS:
            return "cpp"
        if ext in _SH_EXTS:
            return "shell"
        if ext in _GO_EXTS:
            return "go"
        if ext in _PY_EXTS:
            return "python"
    return "unknown"


def _build_env() -> dict:
    """Return os.environ extended with MSYS2 build tool paths."""
    env = os.environ.copy()
    extra = [r"D:\msys64\mingw64\bin", r"D:\msys64\usr\bin"]
    env["PATH"] = os.pathsep.join(
        part for part in extra + env.get("PATH", "").split(os.pathsep) if part
    )
    tmp = tempfile.gettempdir()
    env.setdefault("TMPDIR", tmp)
    env.setdefault("TMP", tmp)
    env.setdefault("TEMP", tmp)
    return env


def _handle_retry_or_failure(
    report: str,
    retry_count: int,
    max_retries: int,
    emit: Callable[[str, str | None, str | None, str | None], None],
) -> dict | tuple[str, int]:
    next_retry_count = retry_count + 1
    if next_retry_count >= max_retries:
        print(f"\n[HARNESS] Max retries ({max_retries}) reached. Finishing with failures.")
        emit("pipeline_failed", None, report[:200] or None, "pipeline failed after max retries")
        return {
            "phase": "done",
            "failed": True,
            "retry_count": next_retry_count,
            "tester_report": report,
        }

    print(f"\n[HARNESS] Phase failed. Retrying implementation ({next_retry_count}/{max_retries})")
    retry_count = next_retry_count
    emit(
        "retrying",
        "implementer",
        report[:200] or None,
        "retrying after implementer/tester failure",
        retry_count_override=retry_count,
    )
    return "implementer", retry_count


def _run_test(test_path: Path, sandbox_dir: str | Path | None = None) -> tuple[int, str]:
    """Execute a test file and return (returncode, combined output)."""
    ext = test_path.suffix.lower()
    env = _build_env()
    timeout = 60
    target_dir = _resolve_sandbox_dir(sandbox_dir)

    try:
        if ext in _PY_EXTS:
            wrapper = (
                "import sys\n"
                f"__file__ = {str(test_path)!r}\n"
                f"sys.path = [p for p in sys.path if p] + [{str(target_dir)!r}]\n"
                f"exec(compile(open(__file__).read(), __file__, 'exec'))\n"
            )
            result = subprocess.run(
                [sys.executable, "-c", wrapper],
                capture_output=True,
                text=True,
                cwd=str(target_dir),
                env=env,
                timeout=timeout,
            )
        elif ext in _SH_EXTS:
            result = subprocess.run(
                ["bash", str(test_path)],
                capture_output=True,
                text=True,
                cwd=str(target_dir),
                env=env,
                timeout=timeout,
            )
        elif ext in _CPP_EXTS:
            bin_path = target_dir / "test_bin"
            compile_result = subprocess.run(
                ["g++", "-std=c++17", "-o", str(bin_path), str(test_path)],
                capture_output=True,
                text=True,
                cwd=str(target_dir),
                env=env,
                timeout=timeout,
            )
            if compile_result.returncode != 0:
                return compile_result.returncode, compile_result.stdout + compile_result.stderr
            result = subprocess.run(
                [str(bin_path)],
                capture_output=True,
                text=True,
                cwd=str(target_dir),
                env=env,
                timeout=timeout,
            )
        else:
            return 1, f"Unsupported test file extension: {ext}"
    except subprocess.TimeoutExpired:
        return 1, f"Test execution timed out after {timeout}s."

    return result.returncode, result.stdout + result.stderr


def tester_phase(
    task: str,
    design: str,
    code_files: dict[str, str],
    sandbox_dir: str | Path | None = None,
    task_metadata: dict | None = None,
) -> tuple[bool, str]:
    """One LLM call -> test file generated -> executed locally."""
    print("\n[HARNESS] Phase: tester")

    impl_files = {
        name: content
        for name, content in sorted(code_files.items())
        if not name.startswith("test_")
    }
    lang = _detect_language(impl_files)
    print(f"  -> detected language: {lang}")

    files_block = "\n\n".join(
        f"## FILE: {name}\n```\n{content}\n```"
        for name, content in impl_files.items()
    )

    prompt = (
        f"Task: {task}\n\n"
        f"## Implementation Language\n{lang}\n\n"
        f"## Design Document\n{design}\n\n"
        f"## Implementation\n{files_block}"
    )

    text = execution.invoke_phase("tester", [
        SystemMessage(content=get_system_prompt("tester", task_metadata=task_metadata)),
        HumanMessage(content=prompt),
    ], task_metadata=task_metadata)

    test_files = _parse_files(text)
    test_name, test_content = next(
        ((name, content) for name, content in test_files.items() if name.startswith("test_")),
        (None, None),
    )

    if test_content:
        target_dir = _resolve_sandbox_dir(sandbox_dir)
        test_path = target_dir / test_name
        test_path.write_text(test_content, encoding="utf-8")
        print(f"  -> {test_name} written, executing...")

        returncode, output = _run_test(test_path, sandbox_dir=target_dir)
        passed = returncode == 0
        print(f"  -> {'PASSED' if passed else 'FAILED'} (exit {returncode})")
        if not passed and output:
            print(f"  -> Output:\n{output[:500]}")
        return passed, output

    passed = "ALL TESTS PASSED" in text.upper()
    print(f"  -> {'PASSED' if passed else 'FAILED'} (text verdict - no test file generated)")
    return passed, text


def run_pipeline(
    task: str,
    start_phase: str = "architect",
    max_retries: int = int(config.get_setting("MAX_RETRIES", "3")),
    sandbox_dir: str | Path | None = None,
    on_status: Callable[[dict], None] | None = None,
    task_metadata: dict | None = None,
) -> dict:
    """Run the full architect -> implementer -> tester pipeline."""
    execution.validate_runtime(task_metadata=task_metadata)
    design = ""
    code_files = {}
    tester_report = ""
    retry_count = 0
    target_dir = _resolve_sandbox_dir(sandbox_dir)

    def emit(
        event_type: str,
        phase: str | None,
        error: str | None = None,
        message: str | None = None,
        retry_count_override: int | None = None,
    ) -> None:
        if on_status is None:
            return
        on_status({
            "type": event_type,
            "phase": phase,
            "retry_count": retry_count if retry_count_override is None else retry_count_override,
            "error": error,
            "message": message,
        })

    if start_phase == "architect":
        emit("phase_started", "architect", message="architect started")
        result = architect_phase(task, sandbox_dir=target_dir, task_metadata=task_metadata)
        if result is None:
            emit("pipeline_cancelled", None, message="pipeline cancelled")
            return {"phase": "cancelled", "retry_count": 0, "tester_report": ""}
        design = result
        emit("phase_finished", "architect", message="architect finished")
    else:
        existing = _read_sandbox(target_dir)
        design = existing.get("design.md", "")
        code_files = {name: content for name, content in existing.items() if name != "design.md"}

    while True:
        if start_phase in ("architect", "implementer") or retry_count > 0:
            emit("phase_started", "implementer", message="implementer started")
            code_files = implementer_phase(
                task,
                design,
                feedback=tester_report,
                sandbox_dir=target_dir,
                task_metadata=task_metadata,
            )
            emit("phase_finished", "implementer", message="implementer finished")
            if not code_files:
                tester_report = _IMPLEMENTER_EMPTY_OUTPUT
                retry_outcome = _handle_retry_or_failure(
                    tester_report,
                    retry_count,
                    max_retries,
                    emit,
                )
                if isinstance(retry_outcome, dict):
                    return retry_outcome
                start_phase, retry_count = retry_outcome
                continue

        emit("phase_started", "tester", message="tester started")
        passed, tester_report = tester_phase(
            task,
            design,
            code_files,
            sandbox_dir=target_dir,
            task_metadata=task_metadata,
        )
        emit(
            "phase_finished",
            "tester",
            None if passed else tester_report[:200] or None,
            "tester finished" if passed else "tester failed",
        )

        if passed:
            print("\n[HARNESS] All phases complete.")
            emit("pipeline_done", None, message="pipeline completed successfully")
            return {
                "phase": "done",
                "retry_count": retry_count,
                "tester_report": tester_report,
            }

        retry_outcome = _handle_retry_or_failure(
            tester_report,
            retry_count,
            max_retries,
            emit,
        )
        if isinstance(retry_outcome, dict):
            return retry_outcome
        start_phase, retry_count = retry_outcome
