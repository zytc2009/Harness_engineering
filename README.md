# Harness Engineering

Infrastructure for splitting task clarification from runtime execution in AI-assisted development workflows.

The current repository is layered:

- `skills/auto-dev`: requirement clarification, task document generation, and enqueue guidance
- `harness-runtime`: queue management, validation, execution, retries, and status reporting
- `harness-*`: harness packages that define stack-specific execution constraints such as `harness-cpp`

If you are resuming work, start from:

- `docs/superpowers/CURRENT_STATE.md`
- `docs/superpowers/plans/2026-04-11-skill-runtime-boundary.md`
- `docs/superpowers/harness-contract.md`
- `docs/tasks/task-template.md`
- `skills/auto-dev/SKILL.md`

## Runtime Overview

The runtime consumes markdown task documents, validates them, places them on the queue, and runs each task through the `architect`, `implementer`, and `tester` phases.

Canonical task template:

- `docs/tasks/task-template.md`

Basic enqueue command:

```bash
python harness-runtime/main.py --add-file docs/tasks/task-001.md
```

Task documents should define:

- `Goal`
- `Inputs`
- `Outputs`
- `Acceptance Criteria`
- `Status`

Common optional sections:

- `Scope`
- `Constraints`
- `Open Questions`

Only task documents with `Status: ready` should be enqueued.

## Queue And Status

The runtime keeps queue and worker state in:

- `harness-runtime/task_queue.json`: queued task lifecycle and retry state
- `harness-runtime/status.json`: latest worker snapshot

Human-readable commands from the repo root:

```bash
python harness-runtime/main.py --queue
python harness-runtime/main.py --status
```

Automation-safe JSON commands:

```bash
python harness-runtime/main.py --queue-json
python harness-runtime/main.py --status-json
```

Use the JSON variants when another tool or script is reading runtime state. The text variants are intended for operators.

Common runtime commands:

```bash
python harness-runtime/main.py --validate-task-doc docs/tasks/task-001.md
python harness-runtime/main.py --add "[Goal] Refresh runtime docs"
python harness-runtime/main.py --add-file docs/tasks/task-001.md
python harness-runtime/main.py --queue
python harness-runtime/main.py --queue-json
python harness-runtime/main.py --status
python harness-runtime/main.py --status-json
python harness-runtime/main.py --cancel <task-id>
python harness-runtime/main.py --skip <task-id>
python harness-runtime/main.py --list
python harness-runtime/main.py --resume <task-id>
python harness-runtime/main.py --drain
```

Command notes:

- `--validate-task-doc` checks a markdown task document without enqueueing it
- `--queue` and `--queue-json` read the current queue state
- `--status` and `--status-json` read the latest worker snapshot
- `--drain` processes pending queue tasks and exits
- `--resume` restarts a saved task by id

## Execution Backends

Each phase resolves independently:

- `architect`
- `implementer`
- `tester`

Each phase can run in one of two execution modes:

- `provider`: provider-backed execution using provider, model, and API settings
- `cli`: local CLI-backed execution using a configured command template

Resolution order for every phase:

1. phase-specific task constraint
2. global task constraint
3. phase-specific environment variable
4. global environment variable
5. runtime default

The runtime default execution mode is `provider`.

### Provider Example

```env
ARCHITECT_EXECUTION_MODE=provider
ARCHITECT_PROVIDER=deepseek
ARCHITECT_MODEL=deepseek-reasoner
```

### CLI Example

```env
EXECUTION_MODE=cli
CLI_COMMAND=codex exec -c approval_mode=full-auto -o {output_file} -
CLI_TIMEOUT=180
```

The default CLI timeout is `180` seconds if no task or environment override is set.

### Mixed Per-Phase Example

```markdown
## Constraints
- architect_execution_mode: provider
- architect_provider: deepseek
- architect_model: deepseek-reasoner
- implementer_execution_mode: cli
- implementer_cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- tester_execution_mode: cli
- tester_cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
```

## CLI Command Rules

Supported CLI placeholders:

- `{prompt_file}`: runtime writes the prompt to a temp file and substitutes that path
- `{prompt_content}`: runtime substitutes the full prompt inline in the command
- `{output_file}`: runtime allocates a temp output file and substitutes that path

CLI input and output behavior:

- if neither `{prompt_file}` nor `{prompt_content}` is present, the runtime sends prompt content over stdin
- a CLI command must accept input through `{prompt_file}`, `{prompt_content}`, or stdin-style `-`
- if `{output_file}` is configured, runtime reads the final result from that file
- if `{output_file}` is not configured, runtime reads the final result from stdout

Codex task-constraint example:

```markdown
## Constraints
- execution_mode: cli
- cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- cli_timeout: 240
```

## Harness Selection

Task documents may declare:

```markdown
## Constraints
- harness: harness-cpp
```

The runtime uses that metadata to load the matching `harness-*` package.

For the task-document format and detailed constraint reference, see:

- `harness-runtime/TASK_FORMAT.md`
- `docs/superpowers/harness-contract.md`

## Main Paths

- `skills/auto-dev/`
- `harness-runtime/`
- `harness-cpp/`
- `docs/superpowers/`
- `docs/tasks/`

## Runtime Completion Summary

- queue inspection: `--queue` and `--queue-json`
- status inspection: `--status` and `--status-json`
- execution model: each phase resolves independently to `provider` or `cli`
- CLI-backed execution: supported through command templates such as `codex exec -c approval_mode=full-auto -o {output_file} -`
