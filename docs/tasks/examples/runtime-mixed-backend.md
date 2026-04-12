# Task

> Example task document for running `harness-runtime` with mixed backends per phase.

## Goal

Update runtime documentation so the architecture section reflects the current queue ownership model and phase execution backend selection.

## Scope

- In scope: update markdown documentation under the repo root and `harness-runtime/`
- In scope: document the distinction between provider-backed and CLI-backed execution
- Out of scope: modifying runtime queue behavior
- Out of scope: changing any Python implementation files

## Inputs

- Repo root: current workspace
- Existing docs in `README.md`, `docs/superpowers/CURRENT_STATE.md`, and `harness-runtime/TASK_FORMAT.md`
- Runtime execution backend implementation in `harness-runtime/execution.py`

## Outputs

- Updated markdown documentation
- Consistent execution-mode examples across docs
- Final runtime completion summary

## Acceptance Criteria

- The resulting docs describe both queue ownership and execution backend selection
- The task uses provider mode for architect and CLI mode for implementer/tester
- Examples remain consistent with current runtime command names
- No Python files under `harness-runtime/` are modified

## Constraints

- architect_execution_mode: provider
- architect_provider: deepseek
- architect_model: deepseek-reasoner
- implementer_execution_mode: cli
- implementer_cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- implementer_cli_timeout: 240
- tester_execution_mode: cli
- tester_cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- tester_cli_timeout: 240
- forbidden_paths: harness-runtime/*.py

## Open Questions

- None

## Status

ready
