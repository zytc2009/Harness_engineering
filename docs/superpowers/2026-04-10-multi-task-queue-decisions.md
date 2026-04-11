# Multi-Task Queue Phase 1 Decisions

Date: 2026-04-10

> Status: partially superseded by `docs/superpowers/plans/2026-04-11-skill-runtime-boundary.md`
> and `docs/superpowers/CURRENT_STATE.md`.

This note records decisions already agreed for the first queue implementation pass.

## Decisions

1. Phase 1 implements `--drain`, not a long-running daemon.
2. Architect confirmation is removed from `orchestrator.py` and handled only by `main.py` in interactive mode.
3. Sandbox changes from shared-global to per-task isolation.
4. State is split into three files with distinct roles:
   - superseded:
   - current model uses `task_queue.json` as the single task record source of truth
   - `status.json` remains the worker snapshot
   - `harness_tasks.json` is no longer part of the active design
5. Any stale queue item left in `running` at startup is converted to `failed` with `error="worker_interrupted"`.
6. Queue file corruption is a hard error; it must not be treated as an empty queue.
7. Phase 1 queue statuses are only `pending`, `running`, `done`, `failed`.
8. Task failure does not block later queued tasks.

## Rationale

- `--drain` matches the actual phase 1 behavior and avoids misleading users with a fake daemon abstraction.
- Removing interactive confirmation from orchestrator makes the pipeline reusable for both interactive and batch execution.
- Per-task sandboxing avoids cross-task contamination and makes resume/debugging semantics clear.
- This reflected an earlier queue/history split; the current design intentionally collapsed task state back into one queue record model.
- Conservative crash recovery is safer than silently retrying interrupted tasks.
