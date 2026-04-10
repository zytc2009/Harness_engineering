# Reliable Drain Queue Implementation Plan

> Scope: phase 1 only. This plan implements a reliable file-based queue with `--drain`. It does not implement a long-running daemon.

## Goal

Upgrade `harness-runtime` from a single interactive task runner into a queue-backed batch worker that:

- accepts tasks via file-backed queue
- processes queued tasks sequentially with `--drain`
- reports real-time worker status via `status.json`
- preserves task history in `harness_tasks.json`
- continues to the next task after a task-level failure
- behaves predictably after interruption or crash

## Explicit Non-Goals

Do not implement these in phase 1:

- long-running polling daemon
- queue task dependencies
- `skipped` status
- task cancellation API
- distributed locking or multi-process workers

## Design Decisions

- `--drain` replaces the earlier `--daemon` concept for phase 1.
- Architect confirmation is removed from `orchestrator.py` and handled by `main.py` only in interactive mode.
- Sandbox becomes per-task, not shared globally across queue runs.
- Queue, history, and status are separate sources of truth:
  - `task_queue.json`: scheduling truth
  - `harness_tasks.json`: history/audit truth
  - `status.json`: current worker snapshot
- Any stale `running` queue task found at startup is marked `failed` with `error="worker_interrupted"`.
- Corrupt `task_queue.json` is a hard failure. Do not silently treat it as an empty queue.

## File Changes

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `harness-runtime/task_queue.py` | Queue load/save/add/update/select/recover |
| Create | `harness-runtime/status.py` | Worker status read/write |
| Modify | `harness-runtime/orchestrator.py` | Remove inline confirmation; support per-task sandbox and status events |
| Modify | `harness-runtime/main.py` | Add `--add`, `--queue`, `--status`, `--drain`; wire queue/history/status together |
| Create | `harness-runtime/TASK_FORMAT.md` | Queue submission guidance |
| Create | `harness-runtime/tests/test_task_queue.py` | Queue module tests |
| Create | `harness-runtime/tests/test_status.py` | Status module tests |
| Modify | `harness-runtime/tests/test_orchestrator.py` | Status callback + per-task sandbox tests |
| Create | `harness-runtime/tests/test_main_queue.py` | Drain-mode tests |
| Create | `harness-runtime/tests/test_drain_integration.py` | End-to-end drain test |
| Modify | `README.md` | Queue/drain docs |
| Modify | `harness-runtime/.gitignore` | Ignore runtime queue/status files |

## Runtime Model

### Queue File

Path: `harness-runtime/task_queue.json`

```json
[
  {
    "id": "uuid",
    "description": "task text",
    "status": "pending",
    "phase": null,
    "retry_count": 0,
    "max_retries": 3,
    "error": null,
    "created": "2026-04-10 10:00:00",
    "updated": "2026-04-10 10:00:00",
    "started_at": null,
    "finished_at": null,
    "duration_s": null
  }
]
```

Allowed queue statuses:

- `pending`
- `running`
- `done`
- `failed`

### Status File

Path: `harness-runtime/status.json`

```json
{
  "worker_state": "idle",
  "current_task_id": null,
  "current_task_description": null,
  "phase": null,
  "task_state": null,
  "retry_count": 0,
  "max_retries": 3,
  "queue_pending": 0,
  "queue_running": 0,
  "queue_done": 0,
  "queue_failed": 0,
  "error": null,
  "updated": "2026-04-10 10:05:00"
}
```

Worker states:

- `idle`
- `running`
- `stopped`

### Sandbox Layout

Each task gets its own sandbox directory.

Example:

```text
<temp>/harness_sandbox/
  <task-id>/
    design.md
    main.py
    test_impl.py
```

No queue task may read or write another task's sandbox.

## Implementation Tasks

### Task 1: Refactor Orchestrator for Queue-Safe Execution

Files:

- Modify: `harness-runtime/orchestrator.py`
- Modify: `harness-runtime/tests/test_orchestrator.py`

Required changes:

- remove interactive confirmation from `architect_phase()`
- support task-scoped sandbox path instead of implicit shared sandbox only
- allow `run_pipeline()` to emit status events via callback
- keep single-task behavior backward-compatible when called without queue wiring

Recommended `run_pipeline()` shape:

```python
def run_pipeline(
    task: str,
    start_phase: str = "architect",
    max_retries: int = int(config.get_setting("MAX_RETRIES", "3")),
    sandbox_dir: str | None = None,
    on_status: callable | None = None,
) -> dict:
```

Recommended callback payload:

```python
{
  "type": "phase_started" | "phase_finished" | "retrying" | "pipeline_done" | "pipeline_failed" | "pipeline_cancelled",
  "phase": "architect" | "implementer" | "tester" | None,
  "retry_count": 0,
  "error": None,
}
```

Tests to add:

- callback receives phase events in expected order
- callback works across retries
- pipeline still works with `on_status=None`
- sandbox writes go to the provided task directory
- architect phase no longer blocks on `input()`

### Task 2: Add Queue Module

Files:

- Create: `harness-runtime/task_queue.py`
- Create: `harness-runtime/tests/test_task_queue.py`

Required functions:

- `load_queue(queue_path=...) -> list[dict]`
- `save_queue(tasks, queue_path=...) -> None`
- `add_task(description, queue_path=..., max_retries=3) -> str`
- `get_task(task_id, queue_path=...) -> dict | None`
- `next_pending(queue_path=...) -> dict | None`
- `update_task(task_id, queue_path=..., **fields) -> None`
- `list_queue(queue_path=...) -> list[dict]`
- `queue_counts(queue_path=...) -> tuple[int, int, int, int]`
- `mark_stale_running_as_failed(queue_path=...) -> int`

Queue invariants:

- writes must be atomic
- corrupt queue file must raise, not return `[]`
- updating an unknown task id must raise `KeyError`
- `mark_stale_running_as_failed()` must convert every `running` task to:
  - `status="failed"`
  - `error="worker_interrupted"`
  - `finished_at=<now>`

Tests to add:

- missing file returns empty list
- save/load roundtrip
- append preserves FIFO order
- first pending task is selected
- non-pending tasks are skipped by selector
- unknown id update raises
- stale `running` tasks are repaired
- corrupt file raises

### Task 3: Add Status Module

Files:

- Create: `harness-runtime/status.py`
- Create: `harness-runtime/tests/test_status.py`

Required functions:

- `update_status(..., status_path=...) -> None`
- `read_status(status_path=...) -> dict | None`

Status module rules:

- writes must be atomic
- missing file returns `None`
- corrupt file returns `None`
- schema is worker-oriented, not just task-oriented

Tests to add:

- write idle status
- write running status
- include queue counts
- include current task details
- read missing returns `None`
- read corrupt returns `None`

### Task 4: Add Queue CLI and Drain Mode

Files:

- Modify: `harness-runtime/main.py`
- Create: `harness-runtime/tests/test_main_queue.py`

CLI additions:

- `--add <DESC>`
- `--queue`
- `--status`
- `--drain`

Required behavior:

- `--add` only enqueues
- `--queue` prints queue items
- `--status` prints worker snapshot
- `--drain`:
  - validates config
  - repairs stale `running` tasks before processing
  - processes all `pending` tasks in FIFO order
  - exits when queue is empty

Drain-mode execution rules:

- one queue task maps to one task-specific sandbox
- queue state, history state, and status snapshot must all be updated
- task failure does not stop later tasks
- `KeyboardInterrupt` fails the current task as `interrupted`, leaves later pending tasks untouched, and stops drain
- unexpected exception fails the current task and continues to the next task

Interactive-mode rules:

- keep current single-task flow
- architect plan preview/confirmation stays only here
- resume flow remains supported

Tests to add:

- `handle_add()` writes pending task
- `run_drain()` drains two successful tasks
- first failed, second successful task still processes both
- stale running tasks are repaired at startup
- drain writes final idle status when queue becomes empty
- `KeyboardInterrupt` stops drain and leaves remaining tasks pending

### Task 5: Add End-to-End Drain Integration Test

Files:

- Create: `harness-runtime/tests/test_drain_integration.py`

Test scenarios:

- three tasks added, all processed, final worker state is `idle`
- mixed failure/success queue run preserves FIFO and result statuses
- per-task sandbox isolation prevents cross-task file leakage

### Task 6: Add Task Submission Guidance

Files:

- Create: `harness-runtime/TASK_FORMAT.md`

Document:

- what a good queue task description should include
- recommended minimal structure
- examples of good and bad task descriptions
- how to submit tasks with `--add`
- how to inspect queue/status/history

### Task 7: Update README

Files:

- Modify: `README.md`

README updates:

- describe the new queue/drain workflow
- document `--add`, `--queue`, `--status`, `--drain`
- explicitly say phase 1 is drain, not daemon
- mention `TASK_FORMAT.md`
- update project tree with:
  - `task_queue.py`
  - `task_queue.json`
  - `status.py`
  - `status.json`
  - `TASK_FORMAT.md`

### Task 8: Ignore Runtime Queue State Files

Files:

- Modify: `harness-runtime/.gitignore`

Add:

```gitignore
task_queue.json
status.json
```

Keep `harness_tasks.json` tracked.

## Execution Order

Implement in this order:

1. Task 1: orchestrator refactor
2. Task 2: queue module
3. Task 3: status module
4. Task 4: main.py drain wiring
5. Task 5: integration test
6. Task 6: task format docs
7. Task 7: README
8. Task 8: `.gitignore`

## Test Strategy

Minimum verification before merge:

```bash
cd harness-runtime
python -m pytest tests/test_orchestrator.py -v
python -m pytest tests/test_task_queue.py -v
python -m pytest tests/test_status.py -v
python -m pytest tests/test_main_queue.py -v
python -m pytest tests/test_drain_integration.py -v
python -m pytest tests/ -v
```

## Acceptance Criteria

Phase 1 is complete only if all of the following are true:

- queue tasks can be added without starting execution
- `--drain` processes all pending tasks then exits
- architect confirmation exists only in interactive mode
- each queue task runs in its own sandbox
- corrupt queue file fails loudly
- stale `running` queue tasks are repaired on startup
- failed tasks do not block later pending tasks
- status file exposes worker-level and task-level state
- history remains queryable via existing task history file

## Deferred to Phase 2

Do not pull these into this plan:

- real `--daemon` with polling loop
- queue cancellation and skip semantics
- queue task dependencies
- multi-worker concurrency
- external dashboard or bot integration beyond polling `status.json`
