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
