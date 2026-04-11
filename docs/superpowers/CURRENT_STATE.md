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
  - harness registry / loader via `constraints.harness`
  - standard harness context files:
    - `HARNESS.md`
    - `TASK_PROTOCOL.md`
  - phase-specific role docs for architect / implementer / tester
- harness filesystem contract is documented in:
  - `docs/superpowers/harness-contract.md`
- benchmark run notes now exist in:
  - `docs/superpowers/benchmark-results-2026-04-11.md`

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
- `docs/superpowers/harness-contract.md`
- `docs/tasks/task-template.md`
- `harness-runtime/harness_registry.py`
- `harness-runtime/main.py`
- `harness-runtime/task_doc.py`
- `harness-runtime/queue_cli.py`
- `harness-runtime/drain.py`
- `harness-runtime/interactive.py`
- `harness-runtime/runtime_support.py`
- `harness-runtime/prompts.py`

## Validation Status

- `pytest -q harness-runtime/tests`
- latest known result: `160 passed`

## Highest-Priority Next Tasks

1. Add task document validation as a first-class command
   - done: `python harness-runtime/main.py --validate-task-doc <path>`
   - returns clear section/constraint errors

2. Strengthen task document structure
   - decision: keep markdown-based task docs
   - continue tightening `Constraints` parsing/validation without introducing a separate manifest format

3. Generalize harness selection
   - done: runtime now uses a registry / loader model based on `constraints.harness`
   - next step is deciding whether/when to add an explicit harness manifest

4. Add non-human status consumption paths to skill integration
   - done: `auto-dev` guidance now points progress reads to `--status-json` / `--queue-json`
   - skill guidance now rejects markdown task-state files as runtime truth sources

5. Clean up top-level README language and stale framing
   - reduce old wording that still describes earlier architecture
   - fix remaining usability/documentation rough edges

6. Add realistic benchmark tasks
   - done: benchmark task docs added under `docs/tasks/benchmarks/`
   - done: validate/add/drain trial executed on 2026-04-11
   - current blocker: external provider connectivity caused architect-phase `Connection error.` failures for all 3 tasks

## Resume Rule

If work resumes later, start from this file and the boundary document instead of reconstructing context from old conversation history.
