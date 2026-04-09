"""
One-Shot Pipeline Orchestrator
================================
Each phase makes exactly ONE LLM call. No tool loops, no ReAct patterns.

Flow:
  architect   → 1 call → design.md written to sandbox
  implementer → 1 call → code files written to sandbox
  tester      → 1 call (generates test_impl.py) + local execution → pass/fail

  If tests fail → retry implementer (with failure feedback) → up to max_retries
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

import config
from prompts import get_system_prompt

SANDBOX = Path(tempfile.gettempdir()) / "harness_sandbox"
SANDBOX.mkdir(exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────

def _call_llm(phase: str, messages: list) -> str:
    """Single LLM call with streaming output. Returns cleaned text (strips <think> blocks)."""
    llm = config.get_llm(phase=phase)
    full_content = ""
    in_think = False
    think_chars = 0
    try:
        for chunk in llm.stream(messages):
            text = chunk.content if isinstance(chunk.content, str) else ""
            if not text:
                continue
            full_content += text
            # Suppress <think>...</think> blocks from console output,
            # but print a dot every ~200 chars so users know it's alive.
            if "<think>" in text and not in_think:
                in_think = True
                print("  [thinking", end="", flush=True)
                think_chars = 0
            if in_think:
                think_chars += len(text)
                if think_chars >= 200:
                    print(".", end="", flush=True)
                    think_chars = 0
                if "</think>" in text:
                    in_think = False
                    think_chars = 0
                    print("]", flush=True)
                continue
            print(text, end="", flush=True)
        print()  # newline after stream ends
    except Exception:
        # Fallback: non-streaming (some providers may not support stream)
        response = llm.invoke(messages)
        full_content = response.content if isinstance(response.content, str) else str(response.content)
        print(full_content[:300] + "…" if len(full_content) > 300 else full_content)
    return re.sub(r"<think>.*?</think>", "", full_content, flags=re.DOTALL).strip()


def _parse_files(text: str) -> dict[str, str]:
    """Parse structured file blocks from LLM output.

    Expected format:
        ## FILE: filename.py
        ```python
        ...code...
        ```

    Returns {filename: content} dict.
    """
    files = {}
    pattern = r"##\s*FILE:\s*(\S+)\s*\n```[^\n]*\n(.*?)```"
    for m in re.finditer(pattern, text, re.DOTALL):
        name = os.path.basename(m.group(1).strip())
        files[name] = m.group(2).rstrip()
    return files


def _write_sandbox(files: dict[str, str]) -> None:
    for name, content in files.items():
        (SANDBOX / name).write_text(content, encoding="utf-8")


def _read_sandbox() -> dict[str, str]:
    result = {}
    for p in sorted(SANDBOX.iterdir()):
        if p.is_file():
            try:
                result[p.name] = p.read_text(encoding="utf-8")
            except Exception:
                pass
    return result


def _confirm() -> bool:
    while True:
        ans = input("  Proceed with implementation? (yes/no): ").strip().lower()
        if ans in ("yes", "y"):
            return True
        if ans in ("no", "n"):
            return False
        print("  Please type 'yes' or 'no'.")


# ── Phases ─────────────────────────────────────────────────────────

def architect_phase(task: str) -> str | None:
    """One LLM call → design.md in sandbox. Returns design text, or None if cancelled."""
    print("\n[HARNESS] Phase: architect")
    text = _call_llm("architect", [
        SystemMessage(content=get_system_prompt("architect")),
        HumanMessage(content=task),
    ])

    # Extract content from ```markdown block if present, else use full response
    md = re.search(r"```(?:markdown|md)?\n(.*?)```", text, re.DOTALL)
    design = md.group(1).strip() if md else text

    _write_sandbox({"design.md": design})
    print(f"  → design.md written ({len(design)} chars)")

    # Show plan preview and ask user to confirm
    lines = text.strip().splitlines()
    preview = "\n  ".join(lines[:20])
    print(f"\n[HARNESS] Architect's plan:\n  {preview}")
    if len(lines) > 20:
        print(f"  ... ({len(lines) - 20} more lines — see design.md in sandbox)")

    print("\n" + "=" * 55)
    if not _confirm():
        print("  [HARNESS] Implementation cancelled.")
        return None

    return design


def implementer_phase(task: str, design: str, feedback: str = "") -> dict[str, str]:
    """One LLM call → code files written to sandbox.

    Args:
        task: Original task description.
        design: Content of design.md from the architect phase.
        feedback: Test failure report from the previous tester run (empty on first attempt).

    Returns:
        Dict of {filename: content} for files written to sandbox.
    """
    print("\n[HARNESS] Phase: implementer")

    prompt = f"Task: {task}\n\n## Design Document\n{design}"
    if feedback:
        prompt += f"\n\n## Test Failures to Fix\n{feedback}"

    text = _call_llm("implementer", [
        SystemMessage(content=get_system_prompt("implementer")),
        HumanMessage(content=prompt),
    ])

    files = _parse_files(text)
    if not files:
        print("  [HARNESS] Warning: no parseable ## FILE: blocks in implementer output.")
        print(f"  Response preview: {text[:300]}")
    else:
        _write_sandbox(files)
        for name in sorted(files):
            print(f"  → {name} written ({len(files[name])} chars)")

    return files


def tester_phase(task: str, design: str, code_files: dict[str, str]) -> tuple[bool, str]:
    """One LLM call → test_impl.py generated → executed locally.

    Returns:
        (passed, report) where report is stdout+stderr from test execution,
        or the LLM's text verdict if no test file was produced.
    """
    print("\n[HARNESS] Phase: tester")

    # Build context block with all implementation files (any language)
    impl_files = {
        name: content
        for name, content in sorted(code_files.items())
        if not name.startswith("test_")
    }
    files_block = "\n\n".join(
        f"## FILE: {name}\n```\n{content}\n```"
        for name, content in impl_files.items()
    )

    prompt = (
        f"Task: {task}\n\n"
        f"## Design Document\n{design}\n\n"
        f"## Implementation\n{files_block}"
    )

    text = _call_llm("tester", [
        SystemMessage(content=get_system_prompt("tester")),
        HumanMessage(content=prompt),
    ])

    # Try to execute a generated test file
    test_files = _parse_files(text)
    test_content = test_files.get("test_impl.py") or next(
        (v for k, v in test_files.items() if k.startswith("test_")), None
    )

    if test_content:
        test_path = SANDBOX / "test_impl.py"
        test_path.write_text(test_content, encoding="utf-8")
        print("  → test_impl.py written, executing...")
        # Run via wrapper that puts sandbox AFTER stdlib in sys.path.
        # Without this, project files like token.py shadow stdlib modules
        # (e.g. token → tokenize → linecache → ImportError).
        # Also sets __file__ explicitly — not available under python -c.
        wrapper = (
            "import sys\n"
            f"__file__ = {str(test_path)!r}\n"
            f"sys.path = [p for p in sys.path if p] + [{str(SANDBOX)!r}]\n"
            f"exec(compile(open(__file__).read(), __file__, 'exec'))\n"
        )
        # Augment PATH with common build tool locations so C++/make/etc. work.
        _env = os.environ.copy()
        _extra_paths = [
            r"D:\msys64\mingw64\bin",
            r"D:\msys64\usr\bin",
        ]
        _env["PATH"] = os.pathsep.join(
            p for p in _extra_paths + _env.get("PATH", "").split(os.pathsep)
            if p
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", wrapper],
                capture_output=True,
                text=True,
                cwd=str(SANDBOX),
                env=_env,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            print("  → TIMEOUT (60s)")
            return False, "Test execution timed out after 60 seconds."

        output = result.stdout + result.stderr
        passed = result.returncode == 0
        print(f"  → {'PASSED' if passed else 'FAILED'} (exit {result.returncode})")
        if not passed and output:
            print(f"  → Output:\n{output[:500]}")
        return passed, output

    # No test file found — fall back to LLM text verdict
    passed = "ALL TESTS PASSED" in text.upper()
    label = "PASSED" if passed else "FAILED"
    print(f"  → {label} (text verdict — no test file generated)")
    return passed, text


# ── Pipeline entry point ───────────────────────────────────────────

def run_pipeline(
    task: str,
    start_phase: str = "architect",
    max_retries: int = int(config.get_setting("MAX_RETRIES", "3")),
) -> dict:
    """Run the full architect → implementer → tester pipeline.

    Args:
        task: User's task description.
        start_phase: "architect" | "implementer" | "tester" (for resuming mid-pipeline).
        max_retries: How many times to retry implementer on test failure.

    Returns:
        Result dict with keys: phase, retry_count, tester_report, failed (optional).
    """
    design = ""
    code_files = {}
    tester_report = ""
    retry_count = 0

    # ── Architect ──────────────────────────────────────────────────
    if start_phase == "architect":
        result = architect_phase(task)
        if result is None:
            return {"phase": "cancelled", "retry_count": 0, "tester_report": ""}
        design = result
    else:
        # Resume: load existing sandbox state
        existing = _read_sandbox()
        design = existing.get("design.md", "")
        code_files = {k: v for k, v in existing.items() if k != "design.md"}

    # ── Implementer + Tester loop ──────────────────────────────────
    while True:
        if start_phase in ("architect", "implementer") or retry_count > 0:
            code_files = implementer_phase(task, design, feedback=tester_report)

        passed, tester_report = tester_phase(task, design, code_files)

        if passed:
            print("\n[HARNESS] All phases complete.")
            return {
                "phase": "done",
                "retry_count": retry_count,
                "tester_report": tester_report,
            }

        retry_count += 1
        if retry_count >= max_retries:
            print(f"\n[HARNESS] Max retries ({max_retries}) reached. Finishing with failures.")
            return {
                "phase": "done",
                "failed": True,
                "retry_count": retry_count,
                "tester_report": tester_report,
            }

        print(f"\n[HARNESS] Tests failed. Retrying implementation ({retry_count}/{max_retries})")
        start_phase = "implementer"  # Don't re-run architect on retry
