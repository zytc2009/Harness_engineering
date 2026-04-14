# Harness Engineering

Infrastructure for splitting task clarification from runtime execution in AI-assisted development workflows.

The repository is organized into three layers:

- `skills/auto-dev` — requirement intake, design orchestration, and task enqueue guidance
- `harness-runtime` — queue management, validation, execution, retries, and status reporting
- `harness-*` — stack-specific constraint packages (e.g. `harness-cpp`)

---

## Quick Start

```bash
# Enqueue an inline task
python harness-runtime/main.py --add "[Goal] Build a CLI calculator [Language] C++ [Input] expression from stdin [Output] result on stdout"

# Validate and enqueue a task document
python harness-runtime/main.py --validate-task-doc docs/tasks/task-001.md
python harness-runtime/main.py --add-file docs/tasks/task-001.md

# Check queue and worker status
python harness-runtime/main.py --queue
python harness-runtime/main.py --status
```

---

## Task Documents

The runtime accepts two task input formats.

### Inline Tasks

Short work items passed directly to `--add`. Provide enough context for the runtime to act:

```text
[Goal] one-sentence description
[Language] Python / C++ / Go / Shell / other
[Input] what the program or feature receives
[Output] what it should produce
[Constraints] optional limits, dependencies, or platform requirements
[Examples] optional sample input/output
```

### Markdown Task Documents

Structured documents passed to `--add-file`. Canonical template: `docs/tasks/task-template.md`.

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

Common optional sections: `Scope`, `Constraints`, `Open Questions`.

Only documents with `Status: ready` are accepted by `--add-file`.

Use `--validate-task-doc` to check a document before enqueueing it.

---

## Runtime Commands

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

| Command | Purpose |
|---|---|
| `--add` | Enqueue an inline task description |
| `--add-file` | Validate and enqueue a markdown task document |
| `--validate-task-doc` | Check a task document without enqueueing |
| `--queue` / `--queue-json` | Show the current queue (human / machine) |
| `--status` / `--status-json` | Show the latest worker snapshot (human / machine) |
| `--cancel` / `--skip` | Operate on a pending task by id |
| `--list` | Show saved tasks across all statuses |
| `--resume` | Restart a saved task by id |
| `--drain` | Process all pending tasks and exit |

Use `--queue-json` and `--status-json` when another tool or script reads the output.

Queue state is persisted in `harness-runtime/task_queue.json`.
Worker state is persisted in `harness-runtime/status.json`.

---

## Execution Backends

Each pipeline phase (`architect`, `implementer`, `tester`) resolves its execution backend independently. Two modes are available:

- `provider` — API-backed execution using provider, model, and credential settings
- `cli` — local executable invoked through a command template

**Resolution order** (first match wins):

1. Phase-specific task constraint
2. Global task constraint
3. Phase-specific environment variable
4. Global environment variable
5. Runtime default (`provider`)

### Provider Mode

```markdown
## Constraints
- execution_mode: provider
- provider: deepseek
- model: deepseek-chat
```

Or via environment variables:

```env
ARCHITECT_EXECUTION_MODE=provider
ARCHITECT_PROVIDER=deepseek
ARCHITECT_MODEL=deepseek-reasoner
```

### CLI Mode

```markdown
## Constraints
- execution_mode: cli
- cli_command: codex exec -c approval_mode=full-auto -o {output_file} -
- cli_timeout: 240
```

Or via environment variables:

```env
EXECUTION_MODE=cli
CLI_COMMAND=codex exec -c approval_mode=full-auto -o {output_file} -
CLI_TIMEOUT=180
```

The default `cli_timeout` is `180` seconds.

**Supported placeholders:**

| Placeholder | Behavior |
|---|---|
| `{prompt_file}` | Runtime writes prompt to a temp file and substitutes the path |
| `{prompt_content}` | Runtime substitutes the full prompt text inline |
| `{output_file}` | Runtime allocates a temp output file and substitutes the path |

If neither `{prompt_file}` nor `{prompt_content}` is present, the prompt is sent over stdin. Output is read from `{output_file}` if configured, otherwise from stdout.

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

---

## Output and Version Control

After a successful pipeline run, generated files can be delivered to a target directory.

| Constraint | Behavior |
|---|---|
| `workspace_dir` | Copy files and create a git commit. Auto-initializes a repo if none exists. |
| `output_dir` | Copy files with no git operations. |

`workspace_dir` takes precedence when both are set. Paths are resolved relative to the project root.

### Commit per task

```markdown
## Constraints
- workspace_dir: ../my-project
```

The runtime copies all generated files and commits with the message `feat: <task description>`.

### Copy only

```markdown
## Constraints
- output_dir: output/puzzle-game
```

### Fresh local repository

If the target directory has no `.git`, the runtime initializes one automatically. Connect a remote later:

```bash
git remote add origin <url> && git push -u origin main
```

---

## Task Decomposition

For complex tasks, the architect phase may output a `subtasks.json` alongside `design.md`. When present, the runtime runs each subtask through its own `architect → implementer → commit` cycle.

Relevant constraints:

| Constraint | Behavior |
|---|---|
| `workspace_dir` | Repository where subtask commits land |
| `subtask_tester` | Run tester after every subtask |
| `subtask_tester_last_only` | Run tester only on the final subtask (overrides `subtask_tester`) |

Each subtask commit message follows the format:

```
[subtask 2/5] Implement calculation core

acceptance_criteria: Addition, subtraction, multiplication, division work correctly.
```

---

## Harness Selection

Declare a harness in the task document to load stack-specific execution constraints:

```markdown
## Constraints
- harness: harness-cpp
```

Available harnesses:

| Package | Stack |
|---|---|
| `harness-cpp` | C++20, CMake, vcpkg, Windows / macOS / Android |

---

## Key Paths

| Path | Purpose |
|---|---|
| `skills/auto-dev/` | Requirement intake and task orchestration skill |
| `harness-runtime/` | Queue, executor, and status engine |
| `harness-cpp/` | C++ harness constraints and role definitions |
| `docs/tasks/` | Task documents and templates |
| `docs/superpowers/` | Design plans and architecture notes |

---

## Reference

- Task document format: `harness-runtime/TASK_FORMAT.md`
- C++ harness invariants and role system: `harness-cpp/HARNESS.md`
- Harness contract: `docs/superpowers/harness-contract.md`
- Task template: `docs/tasks/task-template.md`
