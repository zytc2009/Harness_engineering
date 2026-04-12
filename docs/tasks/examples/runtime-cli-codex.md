# Task

> Example task document for running `harness-runtime` with a local Codex CLI backend.

## Goal

Refresh the runtime-facing README content so the documentation clearly explains queue commands, status commands, and the current provider-or-cli execution model.

## Scope

- In scope: update runtime documentation files to reflect the current execution model
- In scope: document CLI-backed execution with `codex`
- Out of scope: changing runtime queue semantics
- Out of scope: changing runtime Python source files

## Inputs

- Repo root: current workspace
- Existing runtime docs in `README.md` and `harness-runtime/TASK_FORMAT.md`
- Current execution-mode implementation in `harness-runtime/execution.py`

## Outputs

- Updated runtime documentation files
- Consistent examples for queue, status, and CLI-backed execution
- Final runtime completion summary

## Acceptance Criteria

- The updated docs explicitly mention both `provider` and `cli` execution backends
- The updated docs include the string `execution_mode`
- The updated docs include the string `cli_command`
- The updated docs include at least one `codex exec -c approval_mode=full-auto -o {output_file} -` example
- Command examples remain consistent with the current runtime CLI names shown in the touched docs
- No Python source files under `harness-runtime/` are modified

## Constraints

- execution_mode: cli
- cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- cli_timeout: 240
- forbidden_paths: harness-runtime/*.py

## Open Questions

- None

## Status

ready
