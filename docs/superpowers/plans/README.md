# Plans

This directory keeps only the currently active planning documents.

## Active

- `2026-04-11-skill-runtime-boundary.md`
  - current source of truth for the `auto-dev` skill / `harness-runtime` boundary
  - defines the task document contract
  - defines runtime state ownership
  - adopts the single task record model:
    - `task_queue.json` = task lifecycle and execution state
    - `status.json` = worker snapshot

## Cleanup Rule

When a plan is fully superseded by a newer design decision, delete it instead of keeping multiple conflicting plans side by side.
