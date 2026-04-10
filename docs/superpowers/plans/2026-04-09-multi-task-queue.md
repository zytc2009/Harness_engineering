# Multi-Task Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add file-based multi-task queue to harness-runtime so tasks can be submitted via file, executed sequentially, with real-time status reporting and automatic skip-on-failure.

**Architecture:** New `task_queue.py` manages a `task_queue.json` file as a FIFO queue. New `status.py` writes real-time `status.json` for external consumers. `main.py` gains a loop mode (`--daemon`) that continuously drains the queue, plus `--add` for submitting tasks. `orchestrator.py` accepts a status callback. A `TASK_FORMAT.md` documents what users should include in task descriptions.

**Tech Stack:** Python 3.12, existing langchain stack, JSON file I/O, no new dependencies.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `harness-runtime/task_queue.py` | FIFO queue: load/save/add/next/update/list |
| Create | `harness-runtime/status.py` | Real-time status writer + reader |
| Create | `harness-runtime/TASK_FORMAT.md` | User-facing task description guidelines |
| Modify | `harness-runtime/orchestrator.py` | Accept `on_status` callback, call it at phase transitions |
| Modify | `harness-runtime/main.py` | Add `--daemon`, `--add`, `--status` modes; loop consumer |
| Create | `harness-runtime/tests/test_task_queue.py` | Tests for task_queue module |
| Create | `harness-runtime/tests/test_status.py` | Tests for status module |
| Modify | `harness-runtime/tests/test_orchestrator.py` | Add tests for on_status callback |

---

### Task 1: Task Queue Module

**Files:**
- Create: `harness-runtime/task_queue.py`
- Create: `harness-runtime/tests/test_task_queue.py`

Queue file format (`task_queue.json`):
```json
[
  {
    "id": "uuid",
    "description": "task text",
    "status": "pending",
    "created": "2026-04-09 10:00:00",
    "updated": "2026-04-09 10:00:00"
  }
]
```

Status values: `pending` → `running` → `done` | `failed` | `skipped`

- [ ] **Step 1: Write failing tests for task_queue**

```python
"""Tests for task_queue module."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from task_queue import load_queue, save_queue, add_task, next_pending, update_task, list_queue


class TestLoadSaveQueue:
    def test_load_returns_empty_when_no_file(self, tmp_path):
        path = tmp_path / "q.json"
        assert load_queue(str(path)) == []

    def test_load_returns_empty_on_corrupt_file(self, tmp_path):
        path = tmp_path / "q.json"
        path.write_text("{bad json", encoding="utf-8")
        assert load_queue(str(path)) == []

    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "q.json")
        tasks = [{"id": "1", "description": "test", "status": "pending",
                  "created": "2026-04-09", "updated": "2026-04-09"}]
        save_queue(tasks, path)
        assert load_queue(path) == tasks


class TestAddTask:
    def test_adds_task_with_pending_status(self, tmp_path):
        path = str(tmp_path / "q.json")
        task_id = add_task("build calculator", path)
        queue = load_queue(path)
        assert len(queue) == 1
        assert queue[0]["id"] == task_id
        assert queue[0]["description"] == "build calculator"
        assert queue[0]["status"] == "pending"

    def test_appends_to_existing_queue(self, tmp_path):
        path = str(tmp_path / "q.json")
        add_task("task 1", path)
        add_task("task 2", path)
        assert len(load_queue(path)) == 2


class TestNextPending:
    def test_returns_none_when_empty(self, tmp_path):
        path = str(tmp_path / "q.json")
        assert next_pending(path) is None

    def test_returns_first_pending(self, tmp_path):
        path = str(tmp_path / "q.json")
        add_task("first", path)
        add_task("second", path)
        task = next_pending(path)
        assert task["description"] == "first"

    def test_skips_non_pending(self, tmp_path):
        path = str(tmp_path / "q.json")
        id1 = add_task("done task", path)
        add_task("pending task", path)
        update_task(id1, status="done", queue_path=path)
        task = next_pending(path)
        assert task["description"] == "pending task"

    def test_returns_none_when_all_done(self, tmp_path):
        path = str(tmp_path / "q.json")
        id1 = add_task("task", path)
        update_task(id1, status="done", queue_path=path)
        assert next_pending(path) is None


class TestUpdateTask:
    def test_updates_status_and_timestamp(self, tmp_path):
        path = str(tmp_path / "q.json")
        task_id = add_task("task", path)
        update_task(task_id, status="running", queue_path=path)
        queue = load_queue(path)
        assert queue[0]["status"] == "running"

    def test_updates_extra_fields(self, tmp_path):
        path = str(tmp_path / "q.json")
        task_id = add_task("task", path)
        update_task(task_id, status="done", phase="done",
                    retry_count=1, duration_s=10.5, queue_path=path)
        queue = load_queue(path)
        assert queue[0]["phase"] == "done"
        assert queue[0]["retry_count"] == 1

    def test_raises_on_unknown_id(self, tmp_path):
        path = str(tmp_path / "q.json")
        with pytest.raises(KeyError):
            update_task("nonexistent", status="done", queue_path=path)


class TestListQueue:
    def test_returns_all_tasks(self, tmp_path):
        path = str(tmp_path / "q.json")
        add_task("a", path)
        add_task("b", path)
        result = list_queue(path)
        assert len(result) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/test_task_queue.py -v`
Expected: ImportError / ModuleNotFoundError (task_queue module doesn't exist)

- [ ] **Step 3: Implement task_queue.py**

```python
"""
Task Queue Module
=================
File-based FIFO task queue. Tasks are persisted to task_queue.json.

Status lifecycle: pending → running → done | failed | skipped
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

_DEFAULT_QUEUE_FILE = str(Path(__file__).parent / "task_queue.json")


def load_queue(queue_path: str = _DEFAULT_QUEUE_FILE) -> list[dict]:
    """Load task queue from JSON file. Returns [] if missing or corrupt."""
    path = Path(queue_path)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return []


def save_queue(tasks: list[dict], queue_path: str = _DEFAULT_QUEUE_FILE) -> None:
    """Persist task queue to JSON file."""
    Path(queue_path).write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_task(description: str, queue_path: str = _DEFAULT_QUEUE_FILE) -> str:
    """Append a new task to the queue. Returns the task ID."""
    tasks = load_queue(queue_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_id = str(uuid.uuid4())
    tasks.append({
        "id": task_id,
        "description": description,
        "status": "pending",
        "created": now,
        "updated": now,
    })
    save_queue(tasks, queue_path)
    return task_id


def next_pending(queue_path: str = _DEFAULT_QUEUE_FILE) -> dict | None:
    """Return the first pending task, or None if queue is empty/drained."""
    for task in load_queue(queue_path):
        if task["status"] == "pending":
            return task
    return None


def update_task(task_id: str, queue_path: str = _DEFAULT_QUEUE_FILE, **fields) -> None:
    """Update a task's fields by ID. Raises KeyError if not found.

    Common fields: status, phase, retry_count, duration_s, error.
    """
    tasks = load_queue(queue_path)
    for task in tasks:
        if task["id"] == task_id:
            task.update(fields)
            task["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_queue(tasks, queue_path)
            return
    raise KeyError(f"Task not found: {task_id}")


def list_queue(queue_path: str = _DEFAULT_QUEUE_FILE) -> list[dict]:
    """Return all tasks in the queue."""
    return load_queue(queue_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/test_task_queue.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:\AI\claude_code\Harness_engineering
git add harness-runtime/task_queue.py harness-runtime/tests/test_task_queue.py
git commit -m "feat: add file-based task queue module"
```

---

### Task 2: Status Reporter Module

**Files:**
- Create: `harness-runtime/status.py`
- Create: `harness-runtime/tests/test_status.py`

Status file format (`status.json`):
```json
{
  "current_task_id": "uuid or null",
  "current_task_description": "text",
  "phase": "architect",
  "state": "running",
  "retry_count": 0,
  "max_retries": 3,
  "queue_pending": 2,
  "queue_done": 1,
  "queue_failed": 0,
  "updated": "2026-04-09 10:05:00",
  "error": null
}
```

- [ ] **Step 1: Write failing tests for status**

```python
"""Tests for status module."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from status import update_status, read_status


class TestUpdateStatus:
    def test_writes_status_file(self, tmp_path):
        path = str(tmp_path / "status.json")
        update_status(
            task_id="abc-123",
            task_description="build calc",
            phase="architect",
            state="running",
            status_path=path,
        )
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["current_task_id"] == "abc-123"
        assert data["phase"] == "architect"
        assert data["state"] == "running"

    def test_includes_queue_counts(self, tmp_path):
        path = str(tmp_path / "status.json")
        update_status(
            task_id="abc",
            task_description="x",
            phase="tester",
            state="running",
            queue_pending=3,
            queue_done=1,
            queue_failed=0,
            status_path=path,
        )
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["queue_pending"] == 3
        assert data["queue_done"] == 1

    def test_includes_error_field(self, tmp_path):
        path = str(tmp_path / "status.json")
        update_status(
            task_id="abc",
            task_description="x",
            phase="tester",
            state="failed",
            error="compilation failed",
            status_path=path,
        )
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["error"] == "compilation failed"

    def test_idle_status(self, tmp_path):
        path = str(tmp_path / "status.json")
        update_status(
            task_id=None,
            task_description=None,
            phase=None,
            state="idle",
            status_path=path,
        )
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["state"] == "idle"
        assert data["current_task_id"] is None


class TestReadStatus:
    def test_returns_none_when_no_file(self, tmp_path):
        path = str(tmp_path / "status.json")
        assert read_status(path) is None

    def test_reads_written_status(self, tmp_path):
        path = str(tmp_path / "status.json")
        update_status(
            task_id="abc",
            task_description="x",
            phase="implementer",
            state="running",
            status_path=path,
        )
        data = read_status(path)
        assert data["phase"] == "implementer"

    def test_returns_none_on_corrupt_file(self, tmp_path):
        path = tmp_path / "status.json"
        path.write_text("{bad", encoding="utf-8")
        assert read_status(str(path)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/test_status.py -v`
Expected: ImportError (status module doesn't exist)

- [ ] **Step 3: Implement status.py**

```python
"""
Status Reporter Module
======================
Writes real-time task status to status.json for external consumers.

External tools (IM bots, web dashboards) can poll this file
to get current pipeline state without touching the process.
"""

import json
from datetime import datetime
from pathlib import Path

_DEFAULT_STATUS_FILE = str(Path(__file__).parent / "status.json")


def update_status(
    *,
    task_id: str | None,
    task_description: str | None,
    phase: str | None,
    state: str,
    retry_count: int = 0,
    max_retries: int = 3,
    queue_pending: int = 0,
    queue_done: int = 0,
    queue_failed: int = 0,
    error: str | None = None,
    status_path: str = _DEFAULT_STATUS_FILE,
) -> None:
    """Write current pipeline status to JSON file.

    Args:
        task_id: Current task UUID, or None if idle.
        task_description: Current task text, or None if idle.
        phase: Current pipeline phase (architect/implementer/tester), or None.
        state: High-level state (idle/running/done/failed).
        retry_count: Current retry iteration.
        max_retries: Max retries configured.
        queue_pending: Number of pending tasks in queue.
        queue_done: Number of completed tasks.
        queue_failed: Number of failed tasks.
        error: Error message if state is "failed".
        status_path: Path to status.json (injectable for tests).
    """
    data = {
        "current_task_id": task_id,
        "current_task_description": task_description,
        "phase": phase,
        "state": state,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "queue_pending": queue_pending,
        "queue_done": queue_done,
        "queue_failed": queue_failed,
        "error": error,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    Path(status_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_status(status_path: str = _DEFAULT_STATUS_FILE) -> dict | None:
    """Read current status. Returns None if file missing or corrupt."""
    path = Path(status_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/test_status.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:\AI\claude_code\Harness_engineering
git add harness-runtime/status.py harness-runtime/tests/test_status.py
git commit -m "feat: add real-time status reporter module"
```

---

### Task 3: Orchestrator Status Callback

**Files:**
- Modify: `harness-runtime/orchestrator.py:335-394` (run_pipeline function)
- Modify: `harness-runtime/tests/test_orchestrator.py` (add callback tests)

The orchestrator's `run_pipeline` function needs to accept an optional `on_status` callback and invoke it at each phase transition. This keeps orchestrator decoupled from the status module — `main.py` wires them together.

- [ ] **Step 1: Write failing tests for on_status callback**

Append to `harness-runtime/tests/test_orchestrator.py`:

```python
class TestRunPipelineStatusCallback:
    def test_callback_called_at_each_phase(self):
        calls = []
        def on_status(phase, state, **kw):
            calls.append((phase, state))

        with (
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}),
            patch("orchestrator.tester_phase", return_value=(True, "ok")),
        ):
            run_pipeline("task", max_retries=3, on_status=on_status)

        phases_seen = [c[0] for c in calls]
        assert "architect" in phases_seen
        assert "implementer" in phases_seen
        assert "tester" in phases_seen

    def test_callback_receives_retry_count(self):
        calls = []
        def on_status(phase, state, **kw):
            calls.append(kw)

        with (
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}),
            patch("orchestrator.tester_phase", side_effect=[
                (False, "fail"), (True, "pass"),
            ]),
        ):
            run_pipeline("task", max_retries=3, on_status=on_status)

        retry_counts = [c.get("retry_count", 0) for c in calls]
        assert 1 in retry_counts

    def test_pipeline_works_without_callback(self):
        """on_status=None (default) must not break anything."""
        with (
            patch("orchestrator.architect_phase", return_value="design"),
            patch("orchestrator.implementer_phase", return_value={"main.py": "x"}),
            patch("orchestrator.tester_phase", return_value=(True, "ok")),
        ):
            result = run_pipeline("task", max_retries=3)

        assert result["phase"] == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/test_orchestrator.py::TestRunPipelineStatusCallback -v`
Expected: FAIL (run_pipeline doesn't accept on_status parameter yet — but since Python allows extra kwargs it might actually pass for the no-callback test and TypeError for the others. Either way, the callback-specific assertions will fail.)

- [ ] **Step 3: Add on_status parameter to run_pipeline**

In `harness-runtime/orchestrator.py`, modify the `run_pipeline` function signature and body:

Change the function signature from:
```python
def run_pipeline(
    task: str,
    start_phase: str = "architect",
    max_retries: int = int(config.get_setting("MAX_RETRIES", "3")),
) -> dict:
```

To:
```python
def run_pipeline(
    task: str,
    start_phase: str = "architect",
    max_retries: int = int(config.get_setting("MAX_RETRIES", "3")),
    on_status: callable | None = None,
) -> dict:
```

Add a helper inside the function body, right after the docstring:

```python
    def _notify(phase: str, state: str, **kw):
        if on_status is not None:
            on_status(phase, state, **kw)
```

Then insert `_notify` calls at these points:

1. After architect phase completes (before implementer loop):
   ```python
   _notify("architect", "done")
   ```

2. Before each implementer call:
   ```python
   _notify("implementer", "running", retry_count=retry_count)
   ```

3. Before each tester call:
   ```python
   _notify("tester", "running", retry_count=retry_count)
   ```

4. On test pass (before returning success):
   ```python
   _notify("tester", "passed", retry_count=retry_count)
   ```

5. On retry (before looping back):
   ```python
   _notify("tester", "failed", retry_count=retry_count)
   ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/test_orchestrator.py -v`
Expected: All tests PASS (old tests unaffected, new callback tests pass)

- [ ] **Step 5: Commit**

```bash
cd D:\AI\claude_code\Harness_engineering
git add harness-runtime/orchestrator.py harness-runtime/tests/test_orchestrator.py
git commit -m "feat: add on_status callback to pipeline orchestrator"
```

---

### Task 4: Main.py — Loop Consumer + CLI Commands

**Files:**
- Modify: `harness-runtime/main.py` (full rewrite of main function, keep helpers)

This is the biggest change. `main.py` gains three new modes:

| Mode | CLI | Behavior |
|------|-----|----------|
| Add task | `python main.py --add "description"` | Append to queue, print ID, exit |
| Show status | `python main.py --status` | Print status.json contents, exit |
| Daemon | `python main.py --daemon` | Loop: pick next pending → run pipeline → repeat until queue empty |

Existing modes (`--list`, `--resume`, bare `python main.py`) stay unchanged for backward compatibility.

- [ ] **Step 1: Write failing tests for new CLI modes**

Create `harness-runtime/tests/test_main_queue.py`:

```python
"""Tests for main.py queue integration."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from task_queue import add_task, load_queue


class TestAddMode:
    def test_add_creates_pending_task(self, tmp_path):
        queue_path = str(tmp_path / "q.json")
        with patch("main._QUEUE_FILE", queue_path):
            from main import handle_add
            task_id = handle_add("build calculator")

        queue = load_queue(queue_path)
        assert len(queue) == 1
        assert queue[0]["status"] == "pending"
        assert queue[0]["description"] == "build calculator"


class TestDaemonMode:
    def test_processes_all_pending_tasks(self, tmp_path):
        queue_path = str(tmp_path / "q.json")
        status_path = str(tmp_path / "status.json")
        tasks_path = str(tmp_path / "tasks.json")
        add_task("task 1", queue_path)
        add_task("task 2", queue_path)

        pipeline_results = iter([
            {"phase": "done", "retry_count": 0, "tester_report": "ok"},
            {"phase": "done", "retry_count": 0, "tester_report": "ok"},
        ])

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", Path(tasks_path)),
            patch("main.run_pipeline", side_effect=lambda **kw: next(pipeline_results)),
            patch("main.config"),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
        ):
            from main import run_daemon
            run_daemon(max_retries=3)

        queue = load_queue(queue_path)
        done_count = sum(1 for t in queue if t["status"] == "done")
        assert done_count == 2

    def test_skips_to_next_on_max_retries(self, tmp_path):
        queue_path = str(tmp_path / "q.json")
        status_path = str(tmp_path / "status.json")
        tasks_path = str(tmp_path / "tasks.json")
        add_task("will fail", queue_path)
        add_task("will pass", queue_path)

        results = iter([
            {"phase": "done", "retry_count": 2, "tester_report": "fail", "failed": True},
            {"phase": "done", "retry_count": 0, "tester_report": "ok"},
        ])

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", Path(tasks_path)),
            patch("main.run_pipeline", side_effect=lambda **kw: next(results)),
            patch("main.config"),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
        ):
            from main import run_daemon
            run_daemon(max_retries=2)

        queue = load_queue(queue_path)
        assert queue[0]["status"] == "failed"
        assert queue[1]["status"] == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/test_main_queue.py -v`
Expected: ImportError (handle_add, run_daemon don't exist)

- [ ] **Step 3: Implement main.py changes**

Key changes to `main.py`:

1. Add imports at top:
```python
from task_queue import add_task as queue_add_task, next_pending, update_task, load_queue as load_queue_file, list_queue
from status import update_status
```

2. Add module-level path constants:
```python
_QUEUE_FILE = str(Path(__file__).parent / "task_queue.json")
_STATUS_FILE = str(Path(__file__).parent / "status.json")
```

3. Add `handle_add` function:
```python
def handle_add(description: str) -> str:
    """Add a task to the queue. Returns task ID."""
    task_id = queue_add_task(description, _QUEUE_FILE)
    print(f"[HARNESS] Task added: {task_id}")
    print(f"  Description: {description}")
    print(f"  Run 'python main.py --daemon' to start processing.")
    return task_id
```

4. Add `show_status` function:
```python
def show_status() -> None:
    """Print current pipeline status from status.json."""
    from status import read_status
    data = read_status(_STATUS_FILE)
    if data is None:
        print("[HARNESS] No status available. Pipeline has not run yet.")
        return
    print(f"\n{'=' * 55}")
    print("  HARNESS STATUS")
    print(f"{'=' * 55}")
    state = data.get("state", "unknown")
    print(f"  State       : {state}")
    if data.get("current_task_id"):
        print(f"  Task ID     : {data['current_task_id']}")
        print(f"  Description : {data.get('current_task_description', '—')}")
        print(f"  Phase       : {data.get('phase', '—')}")
        print(f"  Retries     : {data.get('retry_count', 0)}/{data.get('max_retries', 3)}")
    print(f"  Queue       : {data.get('queue_pending', 0)} pending, "
          f"{data.get('queue_done', 0)} done, {data.get('queue_failed', 0)} failed")
    if data.get("error"):
        print(f"  Error       : {data['error']}")
    print(f"  Updated     : {data.get('updated', '—')}")
    print(f"{'=' * 55}\n")
```

5. Add `_queue_counts` helper:
```python
def _queue_counts() -> tuple[int, int, int]:
    """Return (pending, done, failed) counts from queue."""
    queue = load_queue_file(_QUEUE_FILE)
    pending = sum(1 for t in queue if t["status"] == "pending")
    done = sum(1 for t in queue if t["status"] == "done")
    failed = sum(1 for t in queue if t["status"] == "failed")
    return pending, done, failed
```

6. Add `run_daemon` function:
```python
def run_daemon(max_retries: int = 3) -> None:
    """Loop: pick next pending task from queue, run pipeline, repeat."""
    config.validate()

    while True:
        task = next_pending(_QUEUE_FILE)
        if task is None:
            pending, done, failed = _queue_counts()
            update_status(
                task_id=None, task_description=None,
                phase=None, state="idle",
                queue_pending=pending, queue_done=done, queue_failed=failed,
                status_path=_STATUS_FILE,
            )
            print("\n[HARNESS] Queue empty. Daemon finished.")
            break

        thread_id = task["id"]
        user_input = task["description"]
        update_task(thread_id, status="running", queue_path=_QUEUE_FILE)
        _upsert_task(thread_id, user_input, "running")

        print_banner(thread_id)

        def on_status(phase, state, **kw):
            pending, done, failed = _queue_counts()
            update_status(
                task_id=thread_id, task_description=user_input,
                phase=phase, state=state,
                retry_count=kw.get("retry_count", 0),
                max_retries=max_retries,
                queue_pending=pending, queue_done=done, queue_failed=failed,
                error=kw.get("error"),
                status_path=_STATUS_FILE,
            )

        t_start = time.monotonic()
        try:
            result = run_pipeline(
                task=user_input, start_phase="architect",
                max_retries=max_retries, on_status=on_status,
            )
        except KeyboardInterrupt:
            duration = round(time.monotonic() - t_start, 1)
            update_task(thread_id, status="failed", error="interrupted",
                        duration_s=duration, queue_path=_QUEUE_FILE)
            _upsert_task(thread_id, user_input, "failed",
                         phase="interrupted", duration_s=duration,
                         error="KeyboardInterrupt")
            print("\n[HARNESS] Interrupted. Remaining tasks stay pending.")
            break
        except Exception as e:
            duration = round(time.monotonic() - t_start, 1)
            update_task(thread_id, status="failed", error=str(e)[:200],
                        duration_s=duration, queue_path=_QUEUE_FILE)
            _upsert_task(thread_id, user_input, "failed",
                         duration_s=duration, error=str(e)[:200])
            print(f"\n[HARNESS] Task failed: {e}")
            print("[HARNESS] Moving to next task...")
            continue

        duration = round(time.monotonic() - t_start, 1)
        is_failed = result.get("failed", False)
        final_status = "failed" if is_failed else "done"

        update_task(
            thread_id, status=final_status,
            phase=result["phase"], retry_count=result["retry_count"],
            duration_s=duration,
            **({"error": "tests_failed"} if is_failed else {}),
            queue_path=_QUEUE_FILE,
        )
        _upsert_task(
            thread_id, user_input, final_status,
            phase=result["phase"], retry_count=result["retry_count"],
            duration_s=duration,
            **({"error": "tests_failed"} if is_failed else {}),
        )

        report = result.get("tester_report", "")
        if report:
            print(f"\n[HARNESS] Extracting long-term memory...")
            from langchain_core.messages import HumanMessage, AIMessage
            msgs = [HumanMessage(content=user_input), AIMessage(content=report)]
            summary = extract_and_save_memory(msgs, user_input)
            print(f"[HARNESS] Memory saved: {summary}")

        print(f"\n[HARNESS] Task {final_status}: {thread_id}")
        if is_failed:
            print("[HARNESS] Moving to next task...")
        print()
```

7. Update `main()` argparse and dispatch:
```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Harness Runtime — Multi-Task Pipeline")
    parser.add_argument("--resume", metavar="ID", help="Restart a saved task")
    parser.add_argument("--list", action="store_true", help="List all saved tasks")
    parser.add_argument("--add", metavar="DESC", help="Add a task to the queue")
    parser.add_argument("--daemon", action="store_true", help="Process all queued tasks")
    parser.add_argument("--status", action="store_true", help="Show current pipeline status")
    parser.add_argument("--queue", action="store_true", help="List queued tasks")
    parser.add_argument(
        "--phase", default="architect",
        choices=["architect", "implementer", "tester"],
        help="Starting phase (default: architect)",
    )
    args = parser.parse_args()

    if args.list:
        list_tasks()
        return
    if args.add:
        handle_add(args.add)
        return
    if args.status:
        show_status()
        return
    if args.queue:
        _print_queue()
        return
    if args.daemon:
        max_retries = int(config.get_setting("MAX_RETRIES", "3"))
        run_daemon(max_retries=max_retries)
        return

    # ... existing single-task flow unchanged ...
```

8. Add `_print_queue` helper:
```python
def _print_queue() -> None:
    """Print queued tasks."""
    queue = list_queue(_QUEUE_FILE)
    if not queue:
        print("[HARNESS] Queue is empty.")
        return
    print(f"\n{'ID':<36}  {'Status':<10}  {'Created':<19}  Description")
    print("─" * 110)
    for t in queue:
        print(f"{t['id']}  {t['status']:<10}  {t['created']:<19}  {t['description'][:60]}")
    print()
```

- [ ] **Step 4: Run all tests**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:\AI\claude_code\Harness_engineering
git add harness-runtime/main.py harness-runtime/tests/test_main_queue.py
git commit -m "feat: add daemon mode, --add, --status, --queue CLI commands"
```

---

### Task 5: Task Format Documentation

**Files:**
- Create: `harness-runtime/TASK_FORMAT.md`

This documents what makes a good task description, so users think through their requirements before submitting.

- [ ] **Step 1: Write TASK_FORMAT.md**

```markdown
# 任务格式指南

向 Harness Runtime 提交任务前，请按本文档整理需求。需求越清晰，生成的代码质量越高。

---

## 最小必填项

每个任务描述必须包含：

1. **做什么** — 一句话说明要实现的功能
2. **用什么语言** — 指定编程语言（C++、Python、Go、Shell）
3. **输入输出** — 程序从哪里读数据、输出什么格式

## 推荐模板

```
【功能】<一句话描述>
【语言】<C++ / Python / Go / Shell>
【输入】<stdin 格式描述，或"无输入">
【输出】<stdout 格式描述>
【约束】<可选：性能要求、依赖限制、平台要求等>
【示例】
  输入: <示例输入>
  输出: <期望输出>
```

## 好的例子

```
【功能】实现一个简单计算器，支持 +, -, *, / 四则运算
【语言】C++
【输入】每行一个表达式，如 "2+3"，支持整数和浮点数
【输出】每行一个结果，如 "5"
【约束】除零时输出 "Error: division by zero" 到 stderr 并返回 exit 1
【示例】
  输入: 2+3
  输出: 5
  输入: 10/0
  输出: (stderr) Error: division by zero
```

## 不好的例子

以下任务描述会导致设计歧义，增加失败概率：

| 描述 | 问题 |
|------|------|
| "做个计算器" | 没有语言、没有 I/O 格式、功能范围不明 |
| "写一个 Web 服务" | 太泛，缺少端点定义、数据模型 |
| "修复 bug" | 没有上下文，不知道修什么 |

## 提交方式

```bash
# 单个任务
python main.py --add "【功能】计算器 【语言】C++ 【输入】每行一个表达式 【输出】计算结果"

# 批量任务（直接编辑 task_queue.json）
# 往 JSON 数组中追加 {"id": "任意UUID", "description": "...", "status": "pending", "created": "...", "updated": "..."} 对象

# 启动处理
python main.py --daemon
```

## 查看状态

```bash
python main.py --status   # 当前任务状态
python main.py --queue    # 队列列表
python main.py --list     # 历史任务
```
```

- [ ] **Step 2: Commit**

```bash
cd D:\AI\claude_code\Harness_engineering
git add harness-runtime/TASK_FORMAT.md
git commit -m "docs: add task format guidelines for queue submissions"
```

---

### Task 6: Update README

**Files:**
- Modify: `README.md` (add queue section)

- [ ] **Step 1: Add multi-task queue section to README**

Insert after the existing `harness-runtime` section's "快速开始" block, add a new subsection:

```markdown
### 多任务队列

```bash
# 添加任务到队列
python main.py --add "【功能】计算器 【语言】C++ 【输入】每行一个表达式 【输出】结果"
python main.py --add "【功能】排序工具 【语言】Python 【输入】每行一个数字 【输出】排序后的数字"

# 批量处理队列中所有任务
python main.py --daemon

# 查看状态
python main.py --status   # 当前任务实时状态
python main.py --queue    # 队列列表
```

任务描述格式详见 [`harness-runtime/TASK_FORMAT.md`](harness-runtime/TASK_FORMAT.md)。

特性：
- **文件队列**：往 `task_queue.json` 追加任务，daemon 自动消费
- **失败跳过**：任务超过最大重试次数后标记失败，自动处理下一个
- **实时状态**：`status.json` 实时更新，可被外部工具（IM Bot、Web 面板）轮询
- **随时追加**：daemon 运行期间可随时用 `--add` 追加新任务
```

Also update the project structure tree to include the new files:

```
├── harness-runtime/
│   ├── ...existing files...
│   ├── task_queue.py          # 文件队列：FIFO 任务管理
│   ├── task_queue.json        # 队列持久化
│   ├── status.py              # 实时状态上报
│   ├── status.json            # 当前状态（外部工具可轮询）
│   ├── TASK_FORMAT.md         # 任务格式指南
```

- [ ] **Step 2: Commit**

```bash
cd D:\AI\claude_code\Harness_engineering
git add README.md
git commit -m "docs: add multi-task queue section to README"
```

---

### Task 7: Add .gitignore entries for runtime files

**Files:**
- Modify: `harness-runtime/.gitignore`

- [ ] **Step 1: Add status.json and task_queue.json to .gitignore**

These are runtime state files that should not be committed:

```
status.json
task_queue.json
```

Note: `harness_tasks.json` is already tracked (existing task history), so leave it as-is.

- [ ] **Step 2: Commit**

```bash
cd D:\AI\claude_code\Harness_engineering
git add harness-runtime/.gitignore
git commit -m "chore: gitignore runtime state files (status.json, task_queue.json)"
```

---

### Task 8: Integration Test — Full Daemon Flow

**Files:**
- Create: `harness-runtime/tests/test_daemon_integration.py`

End-to-end test that verifies the full daemon loop with mocked LLM.

- [ ] **Step 1: Write integration test**

```python
"""Integration test for daemon queue processing."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from task_queue import add_task, load_queue
from status import read_status


class TestDaemonIntegration:
    def test_full_queue_drain(self, tmp_path):
        """Add 3 tasks, run daemon, verify all processed and status updated."""
        queue_path = str(tmp_path / "q.json")
        status_path = str(tmp_path / "status.json")
        tasks_path = tmp_path / "tasks.json"

        add_task("task A", queue_path)
        add_task("task B", queue_path)
        add_task("task C", queue_path)

        call_count = 0
        def mock_pipeline(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("on_status"):
                kwargs["on_status"]("done", "done", retry_count=0)
            return {"phase": "done", "retry_count": 0, "tester_report": "ok"}

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.run_pipeline", side_effect=mock_pipeline),
            patch("main.config") as mock_config,
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
        ):
            mock_config.get_setting.return_value = "3"
            mock_config._resolve_provider.return_value = "test"
            mock_config._resolve_model.return_value = "test-model"
            from main import run_daemon
            run_daemon(max_retries=3)

        assert call_count == 3

        queue = load_queue(queue_path)
        assert all(t["status"] == "done" for t in queue)

        status = read_status(status_path)
        assert status["state"] == "idle"

    def test_mixed_success_and_failure(self, tmp_path):
        """First task fails, second succeeds. Both get processed."""
        queue_path = str(tmp_path / "q.json")
        status_path = str(tmp_path / "status.json")
        tasks_path = tmp_path / "tasks.json"

        add_task("will fail", queue_path)
        add_task("will pass", queue_path)

        results = iter([
            {"phase": "done", "retry_count": 2, "tester_report": "err", "failed": True},
            {"phase": "done", "retry_count": 0, "tester_report": "ok"},
        ])

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.run_pipeline", side_effect=lambda **kw: next(results)),
            patch("main.config") as mock_config,
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
        ):
            mock_config.get_setting.return_value = "3"
            from main import run_daemon
            run_daemon(max_retries=2)

        queue = load_queue(queue_path)
        assert queue[0]["status"] == "failed"
        assert queue[1]["status"] == "done"
```

- [ ] **Step 2: Run integration test**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/test_daemon_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd D:\AI\claude_code\Harness_engineering\harness-runtime && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd D:\AI\claude_code\Harness_engineering
git add harness-runtime/tests/test_daemon_integration.py
git commit -m "test: add daemon integration tests for multi-task queue"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: Queue (Task 1), Status (Task 2), Callback (Task 3), CLI (Task 4), Docs (Task 5-6), Gitignore (Task 7), Integration (Task 8)
- [x] **Placeholder scan**: All steps contain actual code, no TBD/TODO
- [x] **Type consistency**: `load_queue`/`save_queue`/`add_task`/`next_pending`/`update_task`/`list_queue` signatures consistent across test and implementation; `update_status`/`read_status` signatures match; `on_status` callback signature `(phase, state, **kw)` consistent in orchestrator and main
- [x] **Backward compatibility**: Existing `--list`, `--resume`, bare `python main.py` modes unchanged
- [x] **No new dependencies**: Pure Python, JSON file I/O only
