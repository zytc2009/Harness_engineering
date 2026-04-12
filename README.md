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

### Runtime execution backend can be `provider` or `cli`

`harness-runtime` now supports two execution backends for each phase:

- `provider`: existing LangChain/provider path using API keys and model/base URL config
- `cli`: local CLI invocation path for tools such as `codex` that may rely on local login state instead of API keys

Resolution priority is:

1. task document `Constraints`
2. phase-specific environment variables
3. global environment variables
4. default `provider`

Global example:

```env
EXECUTION_MODE=cli
CLI_COMMAND=codex exec -c approval_mode=full-auto -o {output_file} -
CLI_TIMEOUT=180
```

Mixed phase example:

```env
ARCHITECT_EXECUTION_MODE=provider
ARCHITECT_PROVIDER=deepseek
ARCHITECT_MODEL=deepseek-reasoner

IMPLEMENTER_EXECUTION_MODE=cli
IMPLEMENTER_CLI_COMMAND=codex exec -c approval_mode=full-auto -o {output_file} -

TESTER_EXECUTION_MODE=cli
TESTER_CLI_COMMAND=codex exec -c approval_mode=full-auto -o {output_file} -
```

Supported CLI command placeholders:

- `{prompt_file}`: runtime writes the full prompt to a temp file and substitutes the file path
- `{prompt_content}`: runtime substitutes the full prompt inline into the command string
- `{output_file}`: runtime allocates a temp file for tools that write output to a file

If no prompt placeholder is used, runtime sends the prompt to stdin.

Task document override example:

```md
## Constraints
- execution_mode: cli
- cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- tester_execution_mode: provider
- tester_provider: deepseek
- tester_model: deepseek-chat
```

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

When using CLI mode, the same queue and drain commands apply. Only the phase execution backend changes.

## Notes

- `auto-dev` is not an execution engine
- `harness-runtime` is not the primary requirement discussion interface
- `harness-cpp` is the first concrete harness, not a permanent hard dependency of `auto-dev`
- when in doubt, prefer `CURRENT_STATE.md` over old conversation history
