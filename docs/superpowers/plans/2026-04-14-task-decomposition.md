# Task Decomposition & Per-Subtask Git Commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the harness architect to decompose large tasks into ordered subtasks, with the implementer committing code to git after each subtask completes.

**Architecture:** New `subtask_runner.py` handles subtask iteration; new `git_ops.py` wraps git operations. `orchestrator.py` detects `subtasks.json` after the architect phase and delegates to subtask_runner. Existing single-task flow is unchanged.

**Tech Stack:** Python 3.11+, subprocess (git), unittest, existing LangChain/execution layer

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `harness-runtime/git_ops.py` | **Create** | `ensure_git_repo`, `commit_subtask`, `get_head_sha` |
| `harness-runtime/subtask_runner.py` | **Create** | `SubtaskResult`, `_resolve_workspace`, `_run_subtask`, `run_subtasks` |
| `harness-runtime/orchestrator.py` | **Modify** | `architect_phase` format upgrade, `_load_subtasks`, `_build_decomposed_result`, `run_pipeline` delegation |
| `harness-runtime/prompts.py` | **Modify** | Architect prompt — rules for outputting `subtasks.json` |
| `harness-runtime/status.py` | **Modify** | Add `subtask_id`, `subtask_total` fields to `update_status` |
| `harness-runtime/tests/test_git_ops.py` | **Create** | Tests for all git_ops functions |
| `harness-runtime/tests/test_subtask_runner.py` | **Create** | Tests for subtask iteration, skip logic, workspace resolution |
| `harness-runtime/tests/test_orchestrator.py` | **Modify** | Tests for `_load_subtasks`, `_build_decomposed_result`, architect format upgrade |
| `harness-runtime/TASK_FORMAT.md` | **Modify** | Document new constraints: `workspace_dir`, `subtask_tester`, `subtask_tester_last_only` |

---

## Task 1: Create git_ops.py

**Files:**
- Create: `harness-runtime/git_ops.py`
- Create: `harness-runtime/tests/test_git_ops.py`

- [ ] **Step 1: Write the failing tests**

Create `harness-runtime/tests/test_git_ops.py`:

```python
"""Tests for git_ops module."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import git_ops


class TestEnsureGitRepo:
    def test_initializes_fresh_directory(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        assert (tmp_path / ".git").exists()

    def test_idempotent_on_existing_repo(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        git_ops.ensure_git_repo(tmp_path)  # must not raise
        assert (tmp_path / ".git").exists()

    def test_sets_local_git_identity(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        result = subprocess.run(
            ["git", "config", "user.email"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert result.stdout.strip() == "harness@local"

    def test_does_not_override_identity_on_existing_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "custom@example.com"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
        git_ops.ensure_git_repo(tmp_path)  # repo already exists — must not overwrite config
        result = subprocess.run(
            ["git", "config", "user.email"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert result.stdout.strip() == "custom@example.com"


class TestCommitSubtask:
    def test_returns_40_char_sha(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        (tmp_path / "hello.py").write_text("x = 1", encoding="utf-8")
        sha = git_ops.commit_subtask(tmp_path, ["hello.py"], "[subtask 1/2] add hello")
        assert len(sha) == 40
        assert sha.isalnum()

    def test_commit_message_appears_in_log(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        (tmp_path / "a.py").write_text("pass", encoding="utf-8")
        git_ops.commit_subtask(tmp_path, ["a.py"], "[subtask 1/1] test message")
        log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert "[subtask 1/1] test message" in log.stdout

    def test_only_specified_files_are_staged(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        (tmp_path / "included.py").write_text("x = 1", encoding="utf-8")
        (tmp_path / "excluded.py").write_text("y = 2", encoding="utf-8")
        git_ops.commit_subtask(tmp_path, ["included.py"], "partial commit")
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert "excluded.py" in status.stdout  # still untracked


class TestGetHeadSha:
    def test_returns_sha_after_commit(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        (tmp_path / "f.py").write_text("1", encoding="utf-8")
        committed_sha = git_ops.commit_subtask(tmp_path, ["f.py"], "c")
        assert git_ops.get_head_sha(tmp_path) == committed_sha

    def test_returns_empty_string_when_no_commits(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        assert git_ops.get_head_sha(tmp_path) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd harness-runtime && python -m pytest tests/test_git_ops.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'git_ops'`

- [ ] **Step 3: Create git_ops.py**

Create `harness-runtime/git_ops.py`:

```python
"""Git operations for subtask commit tracking."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_git_repo(directory: Path) -> None:
    """Initialize a git repo with local identity if not already one.

    If the directory is already a git repo, does nothing (including not
    overwriting any existing identity config).
    """
    git_dir = directory / ".git"
    if git_dir.exists():
        return
    subprocess.run(["git", "init"], cwd=str(directory), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "harness@local"],
        cwd=str(directory), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "harness"],
        cwd=str(directory), check=True, capture_output=True,
    )


def commit_subtask(directory: Path, files: list[str], message: str) -> str:
    """Stage files and create a commit. Returns the new HEAD SHA (40 chars)."""
    subprocess.run(
        ["git", "add", "--"] + files,
        cwd=str(directory), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(directory), check=True, capture_output=True,
    )
    return get_head_sha(directory)


def get_head_sha(directory: Path) -> str:
    """Return the current HEAD SHA, or empty string if no commits exist."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(directory), capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd harness-runtime && python -m pytest tests/test_git_ops.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add harness-runtime/git_ops.py harness-runtime/tests/test_git_ops.py
git commit -m "feat: add git_ops module for subtask commit tracking"
```

---

## Task 2: Upgrade architect_phase to support FILE: block output

**Files:**
- Modify: `harness-runtime/orchestrator.py:80-97`
- Modify: `harness-runtime/tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

Add to `harness-runtime/tests/test_orchestrator.py` (after existing `TestParseFiles` class):

```python
class TestArchitectPhaseFileBlocks:
    """architect_phase must handle ## FILE: block output format."""

    def test_writes_design_md_from_file_block(self, tmp_path):
        with patch("orchestrator.execution.invoke_phase", return_value=(
            "## FILE: design.md\n```markdown\n# My Design\n```\n"
        )):
            design = architect_phase("some task", sandbox_dir=tmp_path)
        assert design == "# My Design"
        assert (tmp_path / "design.md").read_text(encoding="utf-8") == "# My Design"

    def test_writes_subtasks_json_when_present(self, tmp_path):
        output = (
            "## FILE: design.md\n```markdown\n# Design\n```\n\n"
            '## FILE: subtasks.json\n```json\n[{"id":1}]\n```\n'
        )
        with patch("orchestrator.execution.invoke_phase", return_value=output):
            architect_phase("task", sandbox_dir=tmp_path)
        assert (tmp_path / "subtasks.json").exists()
        assert (tmp_path / "subtasks.json").read_text(encoding="utf-8") == '[{"id":1}]'

    def test_falls_back_to_legacy_markdown_block(self, tmp_path):
        """Architect output without ## FILE: blocks must still work."""
        with patch("orchestrator.execution.invoke_phase", return_value=(
            "```markdown\n# Legacy Design\n```\nDESIGN COMPLETE"
        )):
            design = architect_phase("task", sandbox_dir=tmp_path)
        assert design == "# Legacy Design"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd harness-runtime && python -m pytest tests/test_orchestrator.py::TestArchitectPhaseFileBlocks -v
```

Expected: `FAILED` — `test_writes_subtasks_json_when_present` fails because current code ignores `## FILE:` blocks.

- [ ] **Step 3: Update architect_phase in orchestrator.py**

Replace `orchestrator.py:80-97`:

```python
def architect_phase(
    task: str,
    sandbox_dir: str | Path | None = None,
    task_metadata: dict | None = None,
) -> str:
    """One LLM call -> design.md (and optionally subtasks.json) in sandbox."""
    print("\n[HARNESS] Phase: architect")
    text = execution.invoke_phase("architect", [
        SystemMessage(content=get_system_prompt("architect", task_metadata=task_metadata)),
        HumanMessage(content=task),
    ], task_metadata=task_metadata)

    files = _parse_files(text)
    if "design.md" in files:
        _write_sandbox(files, sandbox_dir=sandbox_dir)
        design = files["design.md"]
    else:
        md = re.search(r"```(?:markdown|md)?\n(.*?)```", text, re.DOTALL)
        design = md.group(1).strip() if md else text
        _write_sandbox({"design.md": design}, sandbox_dir=sandbox_dir)

    print(f"  -> design.md written ({len(design)} chars)")
    if "subtasks.json" in files:
        print(f"  -> subtasks.json written ({len(files['subtasks.json'])} chars)")
    return design
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd harness-runtime && python -m pytest tests/test_orchestrator.py -v
```

Expected: all tests PASS (new + existing)

- [ ] **Step 5: Commit**

```bash
git add harness-runtime/orchestrator.py harness-runtime/tests/test_orchestrator.py
git commit -m "feat: architect_phase supports ## FILE: block output with subtasks.json"
```

---

## Task 3: Update architect prompt for subtasks.json

**Files:**
- Modify: `harness-runtime/prompts.py:27-57`

No new tests needed — prompt content is integration-tested by the architect_phase tests above.

- [ ] **Step 1: Update `_ARCHITECT_PROMPT` in prompts.py**

Replace the `Output Format:` section at the end of `_ARCHITECT_PROMPT` (lines 53-57):

```python
_ARCHITECT_PROMPT = """## Your Role: Architect

Analyze the task and produce a design document. Be thorough; the implementer and tester work ONLY from your document.

Responsibilities:
- Define module boundaries and dependencies
- Specify public interfaces (function signatures, types)
- Choose technology and library selections
- Document constraints and invariants
- List every file the implementer must create
- Specify exact stdin/stdout format

Design Principles:
- Interface isolation: each module does one thing
- Dependency inversion: core logic depends on abstractions
- Minimal public API surface
- Value semantics: prefer immutable types

## I/O Contract (MANDATORY)

Every design document MUST include an `## I/O Contract` section that specifies:
- stdin: what the program reads
- stdout: exact output format
- stderr: error output convention
- exit codes: 0 = success, non-zero = failure

The tester writes tests based solely on this contract.

## Task Decomposition (for complex tasks)

If the task requires more than one implementer call to complete, output a `subtasks.json` file
that breaks implementation into 2–10 ordered subtasks. Each subtask must be completable in a
single implementer call. For simple tasks, omit `subtasks.json`.

subtasks.json schema (each entry):
- id: integer starting from 1
- title: short imperative title
- description: what to implement in this subtask (multi-sentence natural language)
- files: list of filenames the implementer must produce
- acceptance_criteria: how to verify this subtask is correct (multi-sentence natural language)

## Output Format

Output each file using this exact format:

## FILE: design.md
\```markdown
...full design document...
\```

## FILE: subtasks.json
\```json
[
  {
    "id": 1,
    "title": "...",
    "description": "...",
    "files": ["..."],
    "acceptance_criteria": "..."
  }
]
\```

Omit the subtasks.json block entirely for simple single-call tasks.
State `DESIGN COMPLETE` on its own line after all file blocks.
"""
```

- [ ] **Step 2: Verify existing prompt tests still pass**

```bash
cd harness-runtime && python -m pytest tests/test_prompts.py -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add harness-runtime/prompts.py
git commit -m "feat: architect prompt supports subtasks.json output for complex tasks"
```

---

## Task 4: Add _load_subtasks and _build_decomposed_result to orchestrator.py

**Files:**
- Modify: `harness-runtime/orchestrator.py`
- Modify: `harness-runtime/tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

Add to `harness-runtime/tests/test_orchestrator.py`:

```python
import json
from orchestrator import _load_subtasks, _build_decomposed_result


class TestLoadSubtasks:
    def test_returns_none_when_file_absent(self, tmp_path):
        assert _load_subtasks(tmp_path) is None

    def test_returns_list_when_valid(self, tmp_path):
        data = [{"id": 1, "title": "t", "description": "d", "files": ["a.py"], "acceptance_criteria": "x"}]
        (tmp_path / "subtasks.json").write_text(json.dumps(data), encoding="utf-8")
        result = _load_subtasks(tmp_path)
        assert result == data

    def test_raises_on_malformed_json(self, tmp_path):
        (tmp_path / "subtasks.json").write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="malformed"):
            _load_subtasks(tmp_path)

    def test_raises_when_not_a_list(self, tmp_path):
        (tmp_path / "subtasks.json").write_text('{"key": "value"}', encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON array"):
            _load_subtasks(tmp_path)


class TestBuildDecomposedResult:
    def _make_result(self, subtask_id, title, status, commit_sha="abc123", error=""):
        from subtask_runner import SubtaskResult
        return SubtaskResult(
            subtask_id=subtask_id, title=title, status=status,
            retry_count=0, commit_sha=commit_sha, error=error,
        )

    def test_all_passed_returns_not_failed(self):
        results = [
            self._make_result(1, "t1", "passed"),
            self._make_result(2, "t2", "passed"),
        ]
        out = _build_decomposed_result(results)
        assert out["phase"] == "done"
        assert not out.get("failed")

    def test_some_skipped_not_all_passes(self):
        results = [
            self._make_result(1, "t1", "passed"),
            self._make_result(2, "t2", "skipped", commit_sha="", error="tester failed"),
        ]
        out = _build_decomposed_result(results)
        assert out["phase"] == "done"
        assert not out.get("failed")  # not ALL skipped

    def test_all_skipped_marks_failed(self):
        results = [
            self._make_result(1, "t1", "skipped", commit_sha="", error="no files"),
            self._make_result(2, "t2", "skipped", commit_sha="", error="tester failed"),
        ]
        out = _build_decomposed_result(results)
        assert out["failed"] is True

    def test_skip_report_in_tester_report(self):
        results = [
            self._make_result(2, "bad subtask", "skipped", commit_sha="", error="no FILE blocks"),
        ]
        out = _build_decomposed_result(results)
        assert "[2]" in out["tester_report"]
        assert "bad subtask" in out["tester_report"]

    def test_subtask_results_included(self):
        results = [self._make_result(1, "t1", "passed", commit_sha="deadbeef")]
        out = _build_decomposed_result(results)
        assert out["subtask_results"][0]["commit_sha"] == "deadbeef"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd harness-runtime && python -m pytest tests/test_orchestrator.py::TestLoadSubtasks tests/test_orchestrator.py::TestBuildDecomposedResult -v
```

Expected: `ImportError` or `AttributeError` — functions not yet defined

- [ ] **Step 3: Add _load_subtasks and _build_decomposed_result to orchestrator.py**

Add `import json` to the imports at the top of `orchestrator.py` (after `import os`):

```python
import json
```

Add these two functions after `_read_sandbox` (around line 78):

```python
def _load_subtasks(sandbox_dir: str | Path | None = None) -> list[dict] | None:
    """Read subtasks.json from sandbox. Returns None if absent, raises ValueError if malformed."""
    target_dir = _resolve_sandbox_dir(sandbox_dir)
    path = target_dir / "subtasks.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"subtasks.json is malformed: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("subtasks.json must be a JSON array")
    return data


def _build_decomposed_result(results: list) -> dict:
    """Build the final pipeline result dict from a list of SubtaskResult."""
    skipped = [r for r in results if r.status == "skipped"]
    all_skipped = len(skipped) == len(results)
    skip_report = "\n".join(
        f"[{r.subtask_id}] {r.title} — {r.error}" for r in skipped
    )
    return {
        "phase": "done",
        "failed": all_skipped,
        "retry_count": sum(r.retry_count for r in results),
        "tester_report": skip_report,
        "subtask_results": [
            {
                "id": r.subtask_id,
                "title": r.title,
                "status": r.status,
                "commit_sha": r.commit_sha,
                "error": r.error,
            }
            for r in results
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd harness-runtime && python -m pytest tests/test_orchestrator.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add harness-runtime/orchestrator.py harness-runtime/tests/test_orchestrator.py
git commit -m "feat: add _load_subtasks and _build_decomposed_result to orchestrator"
```

---

## Task 5: Create subtask_runner.py

**Files:**
- Create: `harness-runtime/subtask_runner.py`
- Create: `harness-runtime/tests/test_subtask_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `harness-runtime/tests/test_subtask_runner.py`:

```python
"""Tests for subtask_runner module."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from subtask_runner import SubtaskResult, _resolve_workspace, run_subtasks

SUBTASK = {
    "id": 1,
    "title": "Implement parser",
    "description": "Parse stdin JSON",
    "files": ["parser.py"],
    "acceptance_criteria": "Returns dict on valid input",
}


class TestResolveWorkspace:
    def test_uses_workspace_dir_when_provided(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        with patch("subtask_runner.git_ops.ensure_git_repo") as mock_ensure:
            result = _resolve_workspace(ws, tmp_path / "sandbox")
        assert result == ws
        mock_ensure.assert_called_once_with(ws)

    def test_falls_back_to_sandbox_when_no_workspace(self, tmp_path):
        with patch("subtask_runner.git_ops.ensure_git_repo") as mock_ensure:
            result = _resolve_workspace(None, tmp_path)
        assert result == tmp_path
        mock_ensure.assert_called_once_with(tmp_path)

    def test_creates_workspace_dir_if_missing(self, tmp_path):
        ws = tmp_path / "does_not_exist"
        with patch("subtask_runner.git_ops.ensure_git_repo"):
            result = _resolve_workspace(ws, tmp_path)
        assert ws.exists()


class TestRunSubtasks:
    def _make_metadata(self, **constraints):
        return {"constraints": constraints}

    def test_single_passing_subtask_returns_passed(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="# sub design"),
            patch("subtask_runner.implementer_phase", return_value={"parser.py": "x=1"}),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="abc123"),
        ):
            results = run_subtasks(
                task="build parser",
                design="# design",
                subtasks=[SUBTASK],
                sandbox_dir=tmp_path,
                workspace_dir=None,
                max_retries=3,
                on_status=None,
                task_metadata=None,
            )
        assert len(results) == 1
        assert results[0].status == "passed"
        assert results[0].commit_sha == "abc123"

    def test_implementer_no_files_retries_then_skips(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="# sub design"),
            patch("subtask_runner.implementer_phase", return_value={}),
            patch("subtask_runner.git_ops.ensure_git_repo"),
        ):
            results = run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=2, on_status=None, task_metadata=None,
            )
        assert results[0].status == "skipped"
        assert results[0].retry_count == 2

    def test_failed_subtask_does_not_stop_next(self, tmp_path):
        subtasks = [
            {**SUBTASK, "id": 1, "title": "first"},
            {**SUBTASK, "id": 2, "title": "second", "files": ["b.py"]},
        ]
        call_count = {"n": 0}

        def fake_implementer(task, design, feedback="", sandbox_dir=None, task_metadata=None):
            call_count["n"] += 1
            return {} if call_count["n"] == 1 else {"b.py": "y=2"}

        with (
            patch("subtask_runner.architect_phase", return_value="# sub design"),
            patch("subtask_runner.implementer_phase", side_effect=fake_implementer),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            results = run_subtasks(
                task="t", design="d", subtasks=subtasks,
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=1, on_status=None, task_metadata=None,
            )
        assert results[0].status == "skipped"
        assert results[1].status == "passed"

    def test_tester_runs_when_subtask_tester_true(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.tester_phase", return_value=(True, "ok")) as mock_tester,
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=None,
                task_metadata=self._make_metadata(subtask_tester="true"),
            )
        mock_tester.assert_called_once()

    def test_tester_skipped_when_subtask_tester_false(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.tester_phase") as mock_tester,
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=None, task_metadata=None,
            )
        mock_tester.assert_not_called()

    def test_subtask_tester_last_only_runs_only_on_last(self, tmp_path):
        subtasks = [
            {**SUBTASK, "id": 1, "title": "first"},
            {**SUBTASK, "id": 2, "title": "second", "files": ["b.py"]},
        ]
        tester_calls = []

        def fake_tester(task, design, code_files, sandbox_dir=None, task_metadata=None):
            tester_calls.append(code_files)
            return (True, "ok")

        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.tester_phase", side_effect=fake_tester),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            run_subtasks(
                task="t", design="d", subtasks=subtasks,
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=None,
                task_metadata=self._make_metadata(subtask_tester_last_only="true"),
            )
        assert len(tester_calls) == 1  # only last subtask

    def test_git_commit_failure_does_not_skip_subtask(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", side_effect=RuntimeError("git error")),
        ):
            results = run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=None, task_metadata=None,
            )
        assert results[0].status == "passed"  # not skipped despite git failure
        assert results[0].commit_sha == ""

    def test_on_status_callback_called(self, tmp_path):
        events = []
        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=events.append, task_metadata=None,
            )
        types = [e["type"] for e in events]
        assert "subtask_started" in types
        assert "subtask_finished" in types
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd harness-runtime && python -m pytest tests/test_subtask_runner.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'subtask_runner'`

- [ ] **Step 3: Create subtask_runner.py**

Create `harness-runtime/subtask_runner.py`:

```python
"""Subtask runner for decomposed pipeline execution."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import git_ops
from orchestrator import architect_phase, implementer_phase, tester_phase

logger = logging.getLogger(__name__)


@dataclass
class SubtaskResult:
    subtask_id: int
    title: str
    status: str          # "passed" | "skipped"
    retry_count: int
    commit_sha: str      # empty on git failure or skip
    error: str           # empty on success


def _resolve_workspace(
    workspace_dir: str | Path | None,
    sandbox_dir: Path,
) -> Path:
    """Return the directory to write files and commit into."""
    if workspace_dir is not None:
        path = Path(workspace_dir)
        path.mkdir(parents=True, exist_ok=True)
        git_ops.ensure_git_repo(path)
        return path
    git_ops.ensure_git_repo(sandbox_dir)
    return sandbox_dir


def _should_run_tester(
    constraints: dict,
    subtask_index: int,
    total: int,
) -> bool:
    last_only = str(constraints.get("subtask_tester_last_only", "false")).lower() == "true"
    if last_only:
        return subtask_index == total - 1
    return str(constraints.get("subtask_tester", "false")).lower() == "true"


def _run_subtask(
    task: str,
    design: str,
    subtask: dict,
    subtask_index: int,
    total: int,
    workspace: Path,
    sandbox_dir: Path,
    max_retries: int,
    run_tester: bool,
    on_status: Callable | None,
    task_metadata: dict | None,
) -> SubtaskResult:
    idx = subtask["id"]
    title = subtask["title"]
    description = subtask.get("description", "")
    files = subtask.get("files", [])
    acceptance_criteria = subtask.get("acceptance_criteria", "")

    subtask_prompt = (
        f"Task: {task}\n\n"
        f"## Overall Design\n{design}\n\n"
        f"## Current Subtask ({idx}/{total}): {title}\n{description}\n\n"
        f"## Acceptance Criteria\n{acceptance_criteria}\n\n"
        f"## Files to implement\n"
        + "\n".join(f"- {f}" for f in files)
    )

    retry_count = 0
    tester_report = ""

    while True:
        _emit(on_status, "subtask_started", idx, total, "architect",
              f"subtask {idx}/{total} architect")

        sub_design = architect_phase(
            subtask_prompt, sandbox_dir=sandbox_dir, task_metadata=task_metadata,
        )

        _emit(on_status, "subtask_started", idx, total, "implementer",
              f"subtask {idx}/{total} implementer")

        code_files = implementer_phase(
            subtask_prompt, sub_design,
            feedback=tester_report,
            sandbox_dir=workspace,
            task_metadata=task_metadata,
        )

        if not code_files:
            retry_count += 1
            tester_report = "implementer produced no parseable FILE blocks"
            if retry_count >= max_retries:
                return SubtaskResult(
                    subtask_id=idx, title=title, status="skipped",
                    retry_count=retry_count, commit_sha="", error=tester_report,
                )
            continue

        commit_sha = _try_commit(workspace, files or list(code_files.keys()), idx, total, title, acceptance_criteria)

        if not run_tester:
            return SubtaskResult(
                subtask_id=idx, title=title, status="passed",
                retry_count=retry_count, commit_sha=commit_sha, error="",
            )

        _emit(on_status, "subtask_started", idx, total, "tester",
              f"subtask {idx}/{total} tester")

        passed, tester_report = tester_phase(
            subtask_prompt, sub_design, code_files,
            sandbox_dir=workspace, task_metadata=task_metadata,
        )

        if passed:
            return SubtaskResult(
                subtask_id=idx, title=title, status="passed",
                retry_count=retry_count, commit_sha=commit_sha, error="",
            )

        retry_count += 1
        if retry_count >= max_retries:
            return SubtaskResult(
                subtask_id=idx, title=title, status="skipped",
                retry_count=retry_count, commit_sha=commit_sha,
                error=tester_report[:200],
            )


def _try_commit(
    workspace: Path,
    files: list[str],
    idx: int,
    total: int,
    title: str,
    acceptance_criteria: str,
) -> str:
    message = (
        f"[subtask {idx}/{total}] {title}\n\n"
        f"acceptance_criteria: {acceptance_criteria}"
    )
    try:
        return git_ops.commit_subtask(workspace, files, message)
    except Exception as exc:
        logger.warning("git commit failed for subtask %d: %s", idx, exc)
        return ""


def _emit(
    on_status: Callable | None,
    event_type: str,
    subtask_id: int,
    subtask_total: int,
    phase: str | None,
    message: str,
) -> None:
    if on_status is None:
        return
    on_status({
        "type": event_type,
        "subtask_id": subtask_id,
        "subtask_total": subtask_total,
        "phase": phase,
        "message": message,
    })


def run_subtasks(
    task: str,
    design: str,
    subtasks: list[dict],
    sandbox_dir: Path,
    workspace_dir: str | Path | None,
    max_retries: int,
    on_status: Callable | None,
    task_metadata: dict | None,
) -> list[SubtaskResult]:
    """Iterate over subtasks, running architect→implementer→commit→(tester) for each."""
    workspace = _resolve_workspace(workspace_dir, sandbox_dir)
    total = len(subtasks)
    constraints = (task_metadata or {}).get("constraints") or {}
    results: list[SubtaskResult] = []

    for i, subtask in enumerate(subtasks):
        run_tester = _should_run_tester(constraints, i, total)
        result = _run_subtask(
            task=task,
            design=design,
            subtask=subtask,
            subtask_index=i,
            total=total,
            workspace=workspace,
            sandbox_dir=sandbox_dir,
            max_retries=max_retries,
            run_tester=run_tester,
            on_status=on_status,
            task_metadata=task_metadata,
        )
        results.append(result)
        _emit(on_status, "subtask_finished", subtask["id"], total, None,
              f"subtask {subtask['id']}/{total} {result.status}")

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd harness-runtime && python -m pytest tests/test_subtask_runner.py -v
```

Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add harness-runtime/subtask_runner.py harness-runtime/tests/test_subtask_runner.py
git commit -m "feat: add subtask_runner module for decomposed pipeline execution"
```

---

## Task 6: Wire subtask_runner into orchestrator.run_pipeline

**Files:**
- Modify: `harness-runtime/orchestrator.py:318-434`
- Modify: `harness-runtime/tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Add to `harness-runtime/tests/test_orchestrator.py`:

```python
import json


class TestRunPipelineDecomposed:
    def test_delegates_to_subtask_runner_when_subtasks_present(self, tmp_path):
        subtasks = [{"id": 1, "title": "t", "description": "d", "files": ["f.py"], "acceptance_criteria": "x"}]

        def fake_architect(task, sandbox_dir=None, task_metadata=None):
            (Path(sandbox_dir) / "subtasks.json").write_text(json.dumps(subtasks), encoding="utf-8")
            return "# design"

        with (
            patch("orchestrator.architect_phase", side_effect=fake_architect),
            patch("orchestrator.run_subtasks", return_value=[]) as mock_runner,
        ):
            result = run_pipeline("big task", sandbox_dir=tmp_path)

        mock_runner.assert_called_once()
        assert result["phase"] == "done"

    def test_falls_through_to_single_pipeline_when_no_subtasks(self, tmp_path):
        with (
            patch("orchestrator.architect_phase", return_value="# design"),
            patch("orchestrator.implementer_phase", return_value={"f.py": "x=1"}),
            patch("orchestrator.tester_phase", return_value=(True, "ok")),
        ):
            result = run_pipeline("small task", sandbox_dir=tmp_path)
        assert result["phase"] == "done"
        assert "subtask_results" not in result
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd harness-runtime && python -m pytest tests/test_orchestrator.py::TestRunPipelineDecomposed -v
```

Expected: FAIL — `run_subtasks` not imported, subtasks not detected

- [ ] **Step 3: Add delegation logic to run_pipeline in orchestrator.py**

Add this import at the top of `orchestrator.py` (with other imports):

```python
from subtask_runner import run_subtasks
```

In `run_pipeline`, after the architect phase completes and before the `while True:` loop, insert:

```python
        # Decomposed path: delegate to subtask_runner if architect produced subtasks.json
        subtasks = _load_subtasks(target_dir)
        if subtasks:
            workspace_dir = (((task_metadata or {}).get("constraints") or {})).get("workspace_dir") or None
            results = run_subtasks(
                task=task,
                design=design,
                subtasks=subtasks,
                sandbox_dir=target_dir,
                workspace_dir=workspace_dir,
                max_retries=max_retries,
                on_status=on_status,
                task_metadata=task_metadata,
            )
            return _build_decomposed_result(results)
```

The final `run_pipeline` structure around this section (for reference):

```python
    if start_phase == "architect":
        emit("phase_started", "architect", message="architect started")
        result = architect_phase(task, sandbox_dir=target_dir, task_metadata=task_metadata)
        if result is None:
            emit("pipeline_cancelled", None, message="pipeline cancelled")
            return {"phase": "cancelled", "retry_count": 0, "tester_report": ""}
        design = result
        emit("phase_finished", "architect", message="architect finished")

        # Decomposed path
        subtasks = _load_subtasks(target_dir)
        if subtasks:
            workspace_dir = (((task_metadata or {}).get("constraints") or {})).get("workspace_dir") or None
            results = run_subtasks(
                task=task, design=design, subtasks=subtasks,
                sandbox_dir=target_dir, workspace_dir=workspace_dir,
                max_retries=max_retries, on_status=on_status,
                task_metadata=task_metadata,
            )
            return _build_decomposed_result(results)
    else:
        ...
    
    while True:   # existing single-task loop — unchanged
        ...
```

- [ ] **Step 4: Run all orchestrator tests**

```bash
cd harness-runtime && python -m pytest tests/test_orchestrator.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add harness-runtime/orchestrator.py harness-runtime/tests/test_orchestrator.py
git commit -m "feat: run_pipeline delegates to subtask_runner when subtasks.json present"
```

---

## Task 7: Extend status.py with subtask progress fields

**Files:**
- Modify: `harness-runtime/status.py`
- Modify: `harness-runtime/tests/test_status.py`

- [ ] **Step 1: Write the failing test**

Add to `harness-runtime/tests/test_status.py`:

```python
def test_status_includes_subtask_fields(tmp_path):
    from status import update_status, read_status
    update_status(
        worker_state="running",
        current_task_id="t1",
        current_task_description="big task",
        phase="implementer",
        task_state="running",
        subtask_id=2,
        subtask_total=5,
        status_path=tmp_path / "status.json",
    )
    data = read_status(tmp_path / "status.json")
    assert data["subtask_id"] == 2
    assert data["subtask_total"] == 5
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd harness-runtime && python -m pytest tests/test_status.py -v 2>&1 | tail -10
```

Expected: `TypeError: update_status() got unexpected keyword argument 'subtask_id'`

- [ ] **Step 3: Add subtask fields to update_status in status.py**

In `status.py`, add two parameters to `update_status` (after `retry_count`):

```python
def update_status(
    *,
    worker_state: str,
    current_task_id: str | None,
    current_task_description: str | None,
    last_task_id: str | None = None,
    last_task_description: str | None = None,
    phase: str | None,
    task_state: str | None,
    retry_count: int = 0,
    max_retries: int = 3,
    subtask_id: int | None = None,       # new
    subtask_total: int | None = None,    # new
    queue_pending: int = 0,
    ...
```

And add them to the `data` dict:

```python
    data = {
        ...
        "retry_count": retry_count,
        "max_retries": max_retries,
        "subtask_id": subtask_id,
        "subtask_total": subtask_total,
        ...
    }
```

- [ ] **Step 4: Run all status tests**

```bash
cd harness-runtime && python -m pytest tests/test_status.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add harness-runtime/status.py harness-runtime/tests/test_status.py
git commit -m "feat: status.py tracks subtask_id and subtask_total for decomposed pipelines"
```

---

## Task 8: Update TASK_FORMAT.md docs

**Files:**
- Modify: `harness-runtime/TASK_FORMAT.md`

No tests needed — documentation only.

- [ ] **Step 1: Add new constraints to the Supported Constraints section**

In `TASK_FORMAT.md`, add to the Global execution keys list (after `cli_timeout`):

```markdown
- `workspace_dir`
- `subtask_tester`
- `subtask_tester_last_only`
```

Add a new section after `## CLI-Backed Execution`:

````markdown
## Task Decomposition

For complex tasks, the architect phase may output a `subtasks.json` file alongside `design.md`.
When present, the runtime runs each subtask through its own architect → implementer → commit cycle.

Decomposition constraints:

- `workspace_dir`: path to a git repository where subtask code is committed. Defaults to the
  sandbox directory (a temporary git repo is initialized automatically).
- `subtask_tester`: set to `true` to run the tester phase after each subtask.
- `subtask_tester_last_only`: set to `true` to run the tester only on the final subtask.
  Takes precedence over `subtask_tester`.

Example:

```markdown
## Constraints
- workspace_dir: /path/to/my/project
- subtask_tester_last_only: true
- implementer_cli_timeout: 600
```

Commit message format per subtask:

```
[subtask 2/5] Implement calculation core

acceptance_criteria: Addition, subtraction, multiplication, division work correctly.
```
````

- [ ] **Step 2: Commit**

```bash
git add harness-runtime/TASK_FORMAT.md
git commit -m "docs: document task decomposition constraints in TASK_FORMAT.md"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All 5 spec sections covered: git_ops (Task 1), architect format (Task 2+3), subtask_runner (Task 5), orchestrator wiring (Task 4+6), status + docs (Task 7+8)
- [x] **No placeholders:** All steps contain actual code
- [x] **Type consistency:** `SubtaskResult` defined in Task 5, imported in `_build_decomposed_result` test in Task 4 — correct order of implementation
- [x] **`_should_run_tester` used in `run_subtasks`** — matches internal helper defined in same file
- [x] **`_emit` helper** defined in subtask_runner.py and used consistently in `_run_subtask` and `run_subtasks`
- [x] **`subtask_tester_last_only` takes precedence** — enforced in `_should_run_tester` logic
