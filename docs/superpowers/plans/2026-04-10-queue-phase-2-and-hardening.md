# Queue Phase 2 and Hardening Plan

> Scope: post-phase-1 follow-up work for `harness-runtime`. `--drain`, queue cancel/skip, and the richer status snapshot are already implemented. This plan tracks the remaining hardening items plus the later `--daemon` phase.

## Goal

Build on the completed phase-1 drain worker and track the next layer of operational capability:

- remaining hardening fixes found during review
- a later long-running `--daemon` mode with polling
- follow-up cleanup after queue/status feature work

This plan assumes the phase-1 reliable drain queue is already merged, and that queue cancel/skip plus richer status metadata are already in place.

## Dependencies

This plan depends on the completed phase-1 work documented in:

- `docs/superpowers/plans/2026-04-09-multi-task-queue.md`

## Non-Goals

Do not include these in this phase unless separately planned:

- multi-worker concurrency
- distributed queue coordination
- cross-task dependency graphs
- remote dashboard implementation
- database-backed queue storage

## Workstreams

### Workstream 1: Hardening Follow-Ups From Review

Goal:

- close the remaining correctness gaps before adding a long-running worker lifecycle

Files:

- Modify: `harness-runtime/main.py`
- Modify: `harness-runtime/task_queue.py`
- Modify: `harness-runtime/tests/test_main_queue.py`
- Modify: `harness-runtime/tests/test_task_queue.py`
- Modify: `README.md`

Required fixes:

- respect per-task `max_retries` stored in `task_queue.json`
- stop overwriting task-level retry configuration with the drain-level default
- when stale `running` queue tasks are repaired to `failed`, mirror that repair into `harness_tasks.json`
- ensure interactive architect-stage failures are caught and written as failed task/status records

Review findings now converted into explicit tasks:

1. task-level retry configuration is currently present in queue data but ignored at execution time
2. queue recovery updates `task_queue.json` but not `harness_tasks.json`, causing history drift
3. interactive architect failures can bypass the main exception handling path and leave stale `running` state behind

Tests to add:

- drain honors different `max_retries` values for different queued tasks
- stale `running` repair updates both queue and history records
- architect-phase exception in interactive mode writes failed status and history cleanly

Acceptance criteria:

- queue task metadata matches actual execution behavior
- queue/history/state snapshots stay consistent after recovery
- interactive failures no longer leave ghost running tasks

### Workstream 2: Real Daemon Mode

Goal:

- add a long-running poll loop that waits for newly added tasks instead of exiting on empty queue

Files:

- Modify: `harness-runtime/main.py`
- Modify: `README.md`
- Modify: `harness-runtime/tests/test_main_queue.py`
- Create: `harness-runtime/tests/test_daemon_mode.py`

Required behavior:

- add `--daemon`
- `--daemon` validates config, repairs stale `running` tasks, then enters a poll loop
- if the queue is empty, worker writes idle status and sleeps for a configured interval
- if a new task is added while polling, the worker picks it up without restart
- `KeyboardInterrupt` stops the daemon cleanly and writes `worker_state="stopped"`

Configuration:

- add `QUEUE_POLL_INTERVAL_S` env support
- default polling interval: 3 seconds

Tests to add:

- daemon stays alive when queue is initially empty
- daemon consumes a task added during idle polling
- daemon writes idle status between tasks
- interrupt stops loop cleanly

Acceptance criteria:

- `--drain` behavior remains unchanged
- `--daemon` does not exit on an empty queue
- status output clearly distinguishes idle polling from active execution

### Workstream 3: Remaining Status/Event Cleanup

Goal:

- finish the smaller status contract cleanup after the main status/event work already landed

Files:

- Modify: `harness-runtime/main.py`
- Modify: `harness-runtime/status.py`
- Modify: `harness-runtime/tests/test_main_queue.py`
- Modify: `README.md`

Follow-up focus:

- make `show_status` surface the last completed task summary when no current task is running
- document the meaning of `current_task_*` versus `last_task_*`
- decide whether to expose a short recent event trail or keep a single-event snapshot
- keep event naming stable as `--daemon` is introduced later

Tests to add:

- idle status display includes last completed task details
- status snapshot semantics remain stable after queue control actions

Acceptance criteria:

- operators can tell both what is running now and what last finished
- status field meanings are documented and stable

## Proposed Execution Order

Implement in this order:

1. Workstream 1: hardening follow-ups from review
2. Workstream 3: remaining status/event cleanup
3. Workstream 2: real daemon mode
4. README updates

Rationale:

- do the review before adding more complexity
- close correctness gaps before extending the worker lifecycle
- keep `--daemon` last, since current delivery is still centered on `--drain`

## Test Strategy

Minimum verification for this phase:

```bash
cd harness-runtime
python -m pytest tests/test_main_queue.py -v
python -m pytest tests/test_task_queue.py -v
python -m pytest tests/test_daemon_mode.py -v
python -m pytest tests/ -v
```

## Acceptance Criteria

This phase is complete only if all of the following are true:

- the hardening findings in Workstream 1 are closed
- status semantics are documented and consistent in interactive and queue flows
- `--daemon` remains alive and picks up newly queued tasks
- the follow-up work is recorded in tests and docs

## Deferred Beyond This Phase

Still out of scope after this plan:

- multi-process worker coordination
- remote queue management
- database or message-broker queue backend
- dependent task graphs
- tenant or namespace isolation
