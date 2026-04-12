# Task Format Guide

Use this guide when adding work with `python main.py --add "<task>"`.

## Minimum Task Content

A good queue task should include:

1. What to build or change
2. The target language or stack
3. Expected input/output behavior
4. Any constraints that the implementation must respect

## Recommended Template

```text
[Goal] one-sentence description
[Language] Python / C++ / Go / Shell / other
[Input] what the program or feature receives
[Output] what it should produce
[Constraints] optional limits, dependencies, or platform requirements
[Examples] optional sample input/output
```

## Good Example

```text
[Goal] Build a command-line calculator supporting +, -, *, /
[Language] C++
[Input] One expression per line from stdin, such as 2+3
[Output] One result per line on stdout with no prompts
[Constraints] Division by zero must print an error to stderr and exit non-zero
```

## Bad Example

```text
make a calculator
```

Why it is bad:

- no language specified
- no I/O contract
- no failure behavior

## Queue Commands

```bash
python main.py --add "[Goal] ... [Language] ... [Input] ... [Output] ..."
python main.py --add-file docs/tasks/task-001.md
python main.py --queue
python main.py --status
python main.py --cancel <task-id>
python main.py --skip <task-id>
python main.py --drain
python main.py --list
```

## Phase 1 Note

Phase 1 implements a reliable drain worker. `--drain` processes all current pending tasks and exits. It is not yet a long-running daemon.

## Status Snapshot Semantics

`python main.py --status` reads `status.json` and reports:

- `current_task_*`: the task running right now
- `last_task_*`: the most recently completed task, preserved while the worker is idle
- `last_event_*`: the latest lifecycle event only; phase 1 does not keep an event trail

## Task Document Enqueue

`python main.py --add-file <path>` accepts a markdown task document instead of a single inline string.

Canonical template:

```text
docs/tasks/task-template.md
```

Minimum required sections:

```markdown
## Goal
<what to build>

## Inputs
<what the program or feature receives>

## Outputs
<what it produces>

## Acceptance Criteria
<how to know it is done>

## Status
ready
```

Optional sections such as `Scope`, `Constraints`, and `Open Questions` are also imported into the runtime task description.

## Supported Constraints

`## Constraints` is the place to declare runtime-facing execution hints and limits.

Common keys:

- `harness`: selects a `harness-*` package, for example `harness-cpp`
- `execution_mode`: `provider` or `cli`
- `cli_command`: global CLI command template for all phases
- `cli_timeout`: global CLI timeout in seconds
- `provider`: global provider override
- `model`: global model override
- `api_key`: global API key override
- `base_url`: global OpenAI-compatible base URL override

Phase-specific keys are also supported:

- `architect_execution_mode`
- `architect_cli_command`
- `architect_cli_timeout`
- `architect_provider`
- `architect_model`
- `architect_api_key`
- `architect_base_url`
- `implementer_execution_mode`
- `implementer_cli_command`
- `implementer_cli_timeout`
- `implementer_provider`
- `implementer_model`
- `implementer_api_key`
- `implementer_base_url`
- `tester_execution_mode`
- `tester_cli_command`
- `tester_cli_timeout`
- `tester_provider`
- `tester_model`
- `tester_api_key`
- `tester_base_url`

Priority is:

1. phase-specific constraint
2. global constraint
3. phase-specific environment variable
4. global environment variable
5. runtime default

## CLI Mode Example

Use this when the model should be executed through a locally authenticated CLI rather than an API key:

```markdown
## Constraints
- execution_mode: cli
- cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- cli_timeout: 240
```

Supported CLI placeholders:

- `{prompt_file}`
- `{prompt_content}`
- `{output_file}`

If the command uses none of the prompt placeholders, runtime sends the prompt via stdin.

## Mixed Backend Example

Use different backends per phase when needed:

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
