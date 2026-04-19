# Task Format Guide

Use this guide when authoring, validating, or enqueueing runtime task documents from the repo root.

## Runtime CLI

The runtime entry point is:

```bash
python harness-runtime/main.py
```

Relevant commands:

```bash
python harness-runtime/main.py --add "<task description>"
python harness-runtime/main.py --add-file docs/tasks/task-001.md
python harness-runtime/main.py --validate-task-doc docs/tasks/task-001.md
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

Command intent:

- `--add` enqueues a short inline task description
- `--add-file` enqueues a validated markdown task document
- `--validate-task-doc` checks a markdown task document without enqueueing it
- `--queue` shows the queued task list in a human-readable table
- `--queue-json` shows the same queue data in JSON for automation
- `--status` shows the current worker snapshot in a human-readable report
- `--status-json` shows the same status data in JSON for automation
- `--cancel` and `--skip` operate on pending queued tasks
- `--list` shows saved tasks across statuses
- `--resume` restarts a saved task by id
- `--drain` processes current pending tasks and exits

Use `--queue-json` and `--status-json` for automation. The text commands are operator-facing views.

## Inline Task Format

Inline `--add` tasks are lightweight and best for short work items.

A useful inline task should include:

1. What to build or change
2. The target language or stack
3. Expected input and output behavior
4. Important constraints or failure behavior

Recommended shape:

```text
[Goal] one-sentence description
[Language] Python / C++ / Go / Shell / other
[Input] what the program or feature receives
[Output] what it should produce
[Constraints] optional limits, dependencies, or platform requirements
[Examples] optional sample input/output
```

Good example:

```text
[Goal] Build a command-line calculator supporting +, -, *, /
[Language] C++
[Input] One expression per line from stdin, such as 2+3
[Output] One result per line on stdout with no prompts
[Constraints] Division by zero must print an error to stderr and exit non-zero
```

Bad example:

```text
make a calculator
```

Why it is bad:

- no language specified
- no input or output contract
- no failure behavior

## Markdown Task Documents

`--add-file` accepts a markdown task document instead of a single inline string.

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

## Constraints
<at least one key:value line describing the execution or stack constraints>

## Status
ready
```

Common optional sections:

- `Scope`
- `Open Questions`

Only task documents with `Status: ready` and a non-empty `Constraints` section should be enqueued.

## Queue And Status Semantics

`python harness-runtime/main.py --queue` reads `harness-runtime/task_queue.json` and shows the queued task list.

`python harness-runtime/main.py --status` reads `harness-runtime/status.json` and reports the latest worker snapshot, including:

- `current_task_*`: the task running right now
- `last_task_*`: the most recently completed task, preserved while idle
- `last_event_*`: the latest lifecycle event

`--queue-json` and `--status-json` expose the same information in machine-readable JSON form.

Consistent examples:

```bash
python harness-runtime/main.py --queue
python harness-runtime/main.py --queue-json
python harness-runtime/main.py --status
python harness-runtime/main.py --status-json
```

`--queue` and `--queue-json` read `harness-runtime/task_queue.json`.

`--status` and `--status-json` read `harness-runtime/status.json`.

## Supported Constraints

Declare runtime-facing execution hints and limits under `## Constraints`.

Global execution keys:

- `harness`
- `execution_mode`
- `cli_command`
- `cli_timeout`
- `workspace_dir`
- `output_dir`
- `subtask_tester`
- `subtask_tester_last_only`
- `provider`
- `model`
- `api_key`
- `base_url`
- `user_agent`

Phase-specific execution keys:

- `architect_execution_mode`
- `architect_cli_command`
- `architect_cli_timeout`
- `architect_provider`
- `architect_model`
- `architect_api_key`
- `architect_base_url`
- `architect_user_agent`
- `implementer_execution_mode`
- `implementer_cli_command`
- `implementer_cli_timeout`
- `implementer_provider`
- `implementer_model`
- `implementer_api_key`
- `implementer_base_url`
- `implementer_user_agent`
- `tester_execution_mode`
- `tester_cli_command`
- `tester_cli_timeout`
- `tester_provider`
- `tester_model`
- `tester_api_key`
- `tester_base_url`
- `tester_user_agent`

## Execution Backend Model

Each phase resolves independently:

- `architect`
- `implementer`
- `tester`

Each phase supports two execution backends:

- `provider`: provider-backed execution using provider, model, and API settings
- `cli`: local command execution through a configured CLI template

Resolution order for every phase:

1. phase-specific task constraint
2. global task constraint
3. phase-specific environment variable
4. global environment variable
5. runtime default

The runtime default execution mode is `provider`.

This applies independently to `architect`, `implementer`, and `tester`. A task can keep one phase on `provider` while routing another phase through `cli`.

## CLI-Backed Execution

Use CLI mode when a phase should run through a local executable such as `codex`.

CLI timeout behavior:

- `cli_timeout` defaults to `180` seconds if not set

Supported placeholders:

- `{prompt_file}`: runtime writes the full prompt to a temp file and substitutes the file path
- `{prompt_content}`: runtime substitutes the full prompt text inline
- `{output_file}`: runtime allocates a temp output file and substitutes the file path

Validation and I/O rules:

- if neither `{prompt_file}` nor `{prompt_content}` is present, prompt content is sent through stdin
- a CLI command must accept prompt input through `{prompt_file}`, `{prompt_content}`, or stdin-style `-`
- if `{output_file}` is configured, runtime reads the final output from that file
- if `{output_file}` is not configured, runtime reads the final output from stdout
- `codex exec -c approval_mode=full-auto -o {output_file} -` uses stdin fallback for prompt input and `{output_file}` for the final response

Global Codex example:

```markdown
## Constraints
- execution_mode: cli
- cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- cli_timeout: 240
```

Prompt-file example:

```markdown
## Constraints
- execution_mode: cli
- cli_command: some-cli --prompt-file {prompt_file} --output-file {output_file}
```

## Output and Version Control

After a successful pipeline run, the runtime can copy generated files out of the sandbox and optionally commit them to a git repository.

Two constraints control this behavior:

- `workspace_dir`: path to a git repository. Runtime copies all sandbox files there and creates one commit per task. If the directory does not contain a git repository, one is initialized automatically.
- `output_dir`: path to any directory. Runtime copies all sandbox files there with no git involvement.

Priority: `workspace_dir` takes precedence over `output_dir`. If both are set, only `workspace_dir` is used.

Both paths are resolved relative to the directory where the runtime is invoked (the project root).

### Using an existing git repository

Create or clone a repository first, then point `workspace_dir` at it:

```markdown
## Constraints
- workspace_dir: ../my-project
```

The runtime copies files and commits with the message `feat: <task description>`.

### Using a fresh local repository

If the directory does not exist or has no `.git`, the runtime initializes one:

```markdown
## Constraints
- workspace_dir: output/puzzle-game
```

A local-only repository is created. Connect a remote later with `git remote add origin <url> && git push -u origin main`.

### Copy only, no git

```markdown
## Constraints
- output_dir: output/puzzle-game
```

Files are copied but no git operations are performed.

## Task Decomposition

For complex tasks, the architect phase may output a `subtasks.json` file alongside `design.md`.
When present, the runtime runs each subtask through its own architect → implementer → commit cycle.

Decomposition constraints:

- `workspace_dir`: path to a git repository where subtask code is committed. Defaults to the
  sandbox directory (a temporary git repo is initialized automatically).
- `subtask_tester`: set to `true` to run the tester phase after each subtask.
- `subtask_tester_last_only`: set to `true` to run the tester only on the final subtask.
  Takes precedence over `subtask_tester`.

Example:

```markdown
## Constraints
- workspace_dir: /path/to/my/project
- subtask_tester_last_only: true
- implementer_cli_timeout: 600
```

Commit message format per subtask:

```
[subtask 2/5] Implement calculation core

acceptance_criteria: Addition, subtraction, multiplication, division work correctly.
```
```

## Provider-Backed Execution

Use provider mode when a phase should run through configured provider credentials and model settings.

Global provider example:

```markdown
## Constraints
- execution_mode: provider
- provider: deepseek
- model: deepseek-chat
```

Phase-specific provider example:

```markdown
## Constraints
- tester_execution_mode: provider
- tester_provider: deepseek
- tester_model: deepseek-chat
```

## Mixed Backend Example

Use different backends per phase when needed.

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

This example keeps design generation on a provider-backed model while routing implementation and test phases through a CLI-backed Codex workflow.

## Authoring Notes

- prefer `--validate-task-doc` before `--add-file`
- prefer `--queue-json` and `--status-json` when another system will parse the result
- use phase-specific keys only when a phase needs to differ from the global execution configuration
- keep examples anchored to `python harness-runtime/main.py` when documenting runtime commands from the repo root
