# Task

> Use this template when preparing a task document for:
>
> ```bash
> python harness-runtime/main.py --add-file <task-doc-path>
> ```

## Goal

Describe the single task objective in one concise paragraph.

Example:

- Implement a command-line calculator that reads one expression per line from stdin and prints one result per line to stdout.

## Scope

- In scope: list what this task is allowed to change or deliver
- Out of scope: list what this task must not change

Example:

- In scope: add parser, evaluator, and tests for `+ - * /`
- Out of scope: GUI, history, scientific functions

## Inputs

- Existing repo / files / docs the runtime should rely on
- Runtime assumptions
- Relevant source paths

Example:

- Existing repo under current workspace
- Input expressions come from stdin, one per line

## Outputs

- Files or artifacts expected from execution
- User-visible result

Example:

- Updated implementation files under `src/`
- Updated tests under `tests/`
- Final runtime completion summary

## Acceptance Criteria

- Write 2-5 verifiable completion conditions

Example:

- Valid expressions produce correct results
- Division by zero writes an error to stderr and exits non-zero
- Existing tests still pass
- New tests cover success and failure cases

## Constraints

- language: ...
- platform: ...
- harness: ...
- dependency_policy: ...
- forbidden_paths: ...

Notes:

- Include at least one `key: value` constraint line before enqueueing
- Omit lines that do not apply
- `harness` is optional, but the section itself is required for queueing
- Use `harness-cpp` only when you explicitly want C++ harness constraints injected

## Open Questions

- List unresolved questions only if the task is not yet ready

If this section is non-empty, resolve it before enqueue whenever possible.

## Status

ready

Notes:

- Only `ready` task documents should be passed to `--add-file`
- Use a draft file outside the queue flow if the task still needs clarification
