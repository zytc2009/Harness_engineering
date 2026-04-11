# Harness Engineering

Infrastructure for separating requirement clarification from execution runtime in AI-assisted development workflows.

The current architecture is intentionally layered:

- `skills/auto-dev`: entry layer for requirement clarification, task document creation, and enqueue
- `harness-runtime`: execution layer for validation, queueing, execution, retries, and status
- `harness-*`: language- or stack-specific execution constraint packages such as `harness-cpp`

If you are resuming work, start from these files:

- `docs/superpowers/CURRENT_STATE.md`
- `docs/superpowers/plans/2026-04-11-skill-runtime-boundary.md`
- `docs/superpowers/harness-contract.md`
- `docs/tasks/task-template.md`
- `skills/auto-dev/SKILL.md`

## Current Model

### Task hand-off uses markdown task documents

Canonical template:

- `docs/tasks/task-template.md`

Enqueue with:

```bash
python harness-runtime/main.py --add-file <task-doc-path>
```

Task documents should define:

- `Goal`
- `Scope`
- `Inputs`
- `Outputs`
- `Acceptance Criteria`
- `Constraints`
- `Status`

Only task documents with `Status: ready` should be enqueued.

### Runtime owns execution state

Current state model:

- `task_queue.json`: single source of truth for task lifecycle and execution fields
- `status.json`: worker snapshot

`harness_tasks.json` is no longer part of the active design.

### Skill reads machine-readable runtime status

Use:

```bash
python harness-runtime/main.py --status-json
python harness-runtime/main.py --queue-json
```

Do not treat terminal-formatted human output as the automation interface.

### Harness selection is metadata-driven

Task documents may declare:

```md
## Constraints
- harness: harness-cpp
```

Runtime uses this metadata to discover and load the matching `harness-*` package.

Contract details:

- `docs/superpowers/harness-contract.md`

## Main Paths

- `skills/auto-dev/`
- `harness-runtime/`
- `harness-cpp/`
- `docs/superpowers/`
- `docs/tasks/`

## Common Commands

```bash
python harness-runtime/main.py --validate-task-doc <task-doc-path>
python harness-runtime/main.py --add-file <task-doc-path>
python harness-runtime/main.py --queue
python harness-runtime/main.py --queue-json
python harness-runtime/main.py --status
python harness-runtime/main.py --status-json
python harness-runtime/main.py --drain
```

## Notes

- `auto-dev` is not an execution engine
- `harness-runtime` is not the primary requirement discussion interface
- `harness-cpp` is the first concrete harness, not a permanent hard dependency of `auto-dev`
- when in doubt, prefer `CURRENT_STATE.md` over old conversation history
