# Task

## Goal

Refresh runtime-facing documentation so that queue, status, and task-document commands describe the current architecture and no longer imply deprecated state ownership or workflow behavior.

## Scope

- In scope: updating runtime-related markdown docs and command examples
- Out of scope: changing runtime execution code, changing queue semantics, or adding new CLI flags

## Inputs

- Existing repo under the current workspace
- Current architecture source of truth:
  - `docs/superpowers/CURRENT_STATE.md`
  - `docs/superpowers/plans/2026-04-11-skill-runtime-boundary.md`
  - `docs/superpowers/harness-contract.md`
- Runtime command docs currently live in `README.md` and `harness-runtime/TASK_FORMAT.md`

## Outputs

- Updated markdown documentation under allowed doc paths
- Final runtime completion summary

## Acceptance Criteria

- Documentation reflects `task_queue.json` as the single task record source of truth
- Documentation references `--status-json` and `--queue-json` where machine-readable status matters
- Deprecated `harness_tasks.json` framing is removed from the touched docs
- Command examples remain runnable and consistent with current CLI behavior

## Constraints

- language: markdown
- platform: windows
- forbidden_paths: harness-runtime/*.py

## Status

ready
