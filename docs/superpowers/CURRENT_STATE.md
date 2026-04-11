# Current State

Date: 2026-04-11

## What Is Now True

- `auto-dev` is the entry skill
  - responsibility: clarify requirements and enqueue tasks
  - it no longer owns execution orchestration
- `harness-runtime` is the execution engine
  - queueing
  - execution
  - retries
  - worker status
- runtime state model is now:
  - `task_queue.json` = single task record source of truth
  - `status.json` = worker snapshot
  - `harness_tasks.json` is no longer part of the design
- task documents now have a canonical template:
  - `docs/tasks/task-template.md`
- runtime supports machine-readable status access:
  - `python harness-runtime/main.py --status-json`
  - `python harness-runtime/main.py --queue-json`
- runtime prompt injection now supports:
  - task `Constraints`
  - `harness-cpp/HARNESS.md`
  - `harness-cpp/TASK_PROTOCOL.md`
  - phase-specific role docs for architect / implementer / tester

## Recent Commits

- `ac407bf` docs: add canonical task document template
- `0a9b8a8` runtime: add machine-readable queue and status views
- `a473bc7` runtime: inject phase-specific harness role context
- `3476d4b` runtime: split main cli into focused modules
- `fcee09e` runtime: unify task state and inject harness constraints
- `6db244c` docs: simplify auto-dev boundary and active plans

## Current Main Files

- `skills/auto-dev/SKILL.md`
- `docs/superpowers/plans/2026-04-11-skill-runtime-boundary.md`
- `docs/tasks/task-template.md`
- `harness-runtime/main.py`
- `harness-runtime/task_doc.py`
- `harness-runtime/queue_cli.py`
- `harness-runtime/drain.py`
- `harness-runtime/interactive.py`
- `harness-runtime/runtime_support.py`
- `harness-runtime/prompts.py`

## Validation Status

- `pytest -q harness-runtime/tests`
- latest known result: `152 passed`

## Highest-Priority Next Tasks

1. Add task document validation as a first-class command
   - candidate CLI: `python harness-runtime/main.py --validate-task-doc <path>`
   - return clear section/constraint errors

2. Strengthen task document structure
   - decide whether to keep markdown-only
   - or add stricter structured metadata rules for `Constraints`

3. Generalize harness selection
   - current concrete harness support is only `harness-cpp`
   - next step is a real harness registry / loader model

4. Add non-human status consumption paths to skill integration
   - wire `auto-dev` to use `--status-json` / `--queue-json`
   - avoid parsing terminal-formatted output

5. Clean up top-level README language and stale framing
   - reduce old wording that still describes earlier architecture
   - fix remaining usability/documentation rough edges

6. Add realistic benchmark tasks
   - verify task success rate beyond unit tests
   - measure queue/task-doc/runtime behavior on real repo tasks

## Resume Rule

If work resumes later, start from this file and the boundary document instead of reconstructing context from old conversation history.
