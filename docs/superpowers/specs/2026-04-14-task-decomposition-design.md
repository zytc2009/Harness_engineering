# Task Decomposition & Per-Subtask Git Commit

**Date:** 2026-04-14  
**Status:** Approved

---

## Goal

Enable the harness to handle large tasks by having the architect decompose them into ordered subtasks, with the implementer committing code after each subtask. This ensures a git history trail per subtask and prevents context-window exhaustion from single large implementer calls.

---

## Decisions

| Question | Decision |
|---|---|
| Per-subtask pipeline | architect → implementer → (optional tester) → commit |
| Git target | `workspace_dir` if set, fallback to git-initialized sandbox |
| Subtask list format | `subtasks.json` (machine-readable, runtime-parsed) |
| Subtask fields | `id`, `title`, `description`, `files`, `acceptance_criteria` |
| Execution mode | Fully automatic, no user confirmation between subtasks |
| On failure | Retry up to `max_retries`, then skip and continue, record in final report |
| Architecture | New `subtask_runner.py` + `git_ops.py`; `orchestrator.py` minimally modified |

---

## Architecture Overview

```
Large task input
    │
    ▼
architect phase
    ├── design.md       (existing)
    └── subtasks.json   (new)
    │
    ▼  subtasks.json present?
   YES → subtask_runner.py takes over
   NO  → orchestrator.py existing logic (unchanged)

subtask_runner iterates each subtask:
    ┌──────────────────────────────────┐
    │  architect phase (sub-design)    │
    │  implementer phase               │
    │  git commit                      │
    │  tester phase (optional)         │
    │  failure → retry → skip+record   │
    └──────────────────────────────────┘
    │
    ▼
Final report (N completed / M skipped)
```

**New files:**
- `harness-runtime/subtask_runner.py` — subtask iteration logic
- `harness-runtime/git_ops.py` — git operation wrappers

**Modified files:**
- `harness-runtime/orchestrator.py` — detect subtasks.json, delegate to subtask_runner
- `harness-runtime/prompts.py` — architect prompt updated to output subtasks.json
- `harness-runtime/status.py` — extend status output with subtask progress

---

## subtasks.json Format

Architect outputs this file alongside `design.md` using the existing `## FILE:` block format:

```json
[
  {
    "id": 1,
    "title": "Implement data parsing module",
    "description": "Parse stdin input and return structured data. Handle malformed input with clear errors.",
    "files": ["parser.py"],
    "acceptance_criteria": "Valid JSON input returns parsed result; invalid input raises ValueError with descriptive message."
  },
  {
    "id": 2,
    "title": "Implement calculation core",
    "description": "Accept parsed result from parser.py, execute arithmetic operations.",
    "files": ["calculator.py"],
    "acceptance_criteria": "Addition, subtraction, multiplication, division work correctly. Division by zero returns error, not exception."
  }
]
```

**Architect prompt addition:**

> For complex tasks, output `subtasks.json` breaking the implementation into 2–10 ordered subtasks. Each subtask must be completable in a single implementer call. For simple tasks, omit `subtasks.json`. The `description` and `acceptance_criteria` fields may contain multiple natural-language sentences.

---

## subtask_runner.py

### Data Structure

```python
@dataclass
class SubtaskResult:
    subtask_id: int
    title: str
    status: str          # "passed" | "failed" | "skipped"
    retry_count: int
    commit_sha: str      # git commit hash; empty on failure
    error: str           # failure reason; empty on success
```

### Main Entry Point

```python
def run_subtasks(
    task: str,
    design: str,
    subtasks: list[dict],
    sandbox_dir: Path,
    workspace_dir: Path | None,
    max_retries: int,
    on_status: Callable | None,
    task_metadata: dict | None,
) -> list[SubtaskResult]
```

### Per-Subtask Flow

```
1. architect phase  → sub-design (global design + subtask description)
2. implementer phase → write files to workspace/sandbox
3. git_ops.commit() → git add <files> && git commit -m "[N/M] title"
                       → record commit SHA
4. tester phase (optional, configured via task constraint)
   → on failure: retry up to max_retries, then mark skipped
```

**Skip logic:** When retries are exhausted, record `status="skipped"` with error details and continue to the next subtask without aborting the pipeline.

---

## git_ops.py

```python
def ensure_git_repo(directory: Path) -> None:
    """If directory is not a git repo, run git init + initial commit."""

def commit_subtask(
    directory: Path,
    files: list[str],
    message: str,
) -> str:
    """git add <files> && git commit -m message. Returns commit SHA."""

def get_head_sha(directory: Path) -> str:
    """Return current HEAD commit SHA."""
```

**Workspace resolution (resolved before subtask loop):**

```
workspace_dir configured?
  YES → use that directory; check for existing git repo
  NO  → use sandbox directory; call ensure_git_repo()
```

**Commit message format:**
```
[subtask 2/5] Implement calculation core

acceptance_criteria: Addition, subtraction, multiplication, division work correctly. Division by zero returns error, not exception.
```

**Error handling:** If a git operation fails (e.g., permission error), log a warning but do **not** mark the subtask as skipped. The code is already written; a commit failure must not discard completed work.

---

## Configuration

### New env vars / task constraints

| Key | Meaning | Default |
|---|---|---|
| `workspace_dir` | Target directory for git commits | None (fallback: sandbox) |
| `subtask_tester` | Run tester after each subtask | `false` |
| `subtask_tester_last_only` | Run tester only on the final subtask (takes precedence over `subtask_tester`) | `false` |

### Task constraint example

```markdown
## Constraints
- workspace_dir: /path/to/my/project
- subtask_tester: true
- implementer_cli_timeout: 600
```

### orchestrator.py change (minimal)

```python
# After architect phase completes, before existing while True loop:
subtasks = _load_subtasks(sandbox_dir)   # reads subtasks.json; returns None if absent
if subtasks:
    results = run_subtasks(task, design, subtasks, ...)
    return _build_decomposed_result(results)
# else: fall through to existing while True loop (unchanged)
```

---

## Status Output Extension

While running, `--status` shows subtask progress:

```
Phase     : implementer
Subtask   : 2 / 5  —  Implement calculation core
Retries   : 0 / 3
```

Final report example:

```
Subtasks  : 4 completed, 1 skipped
Skipped   : [3] Implement export module — implementer produced no parseable FILE blocks
```

---

## Error Handling Summary

| Scenario | Behavior |
|---|---|
| Architect outputs no subtasks.json | Fall through to single-task pipeline |
| subtasks.json is malformed JSON | Raise `ValueError` with clear message before loop starts |
| Implementer produces no files | Retry → skip on exhaustion |
| Tester fails | Retry → skip on exhaustion |
| git commit fails | Log warning, continue (subtask marked passed/failed on test result, not git) |
| All subtasks skipped | Pipeline returns `failed=True` with full skip report |

---

## Out of Scope

- User confirmation between subtasks
- Subtask dependency graph (non-linear ordering)
- Subtask parallelism
- Subtask editing via UI
