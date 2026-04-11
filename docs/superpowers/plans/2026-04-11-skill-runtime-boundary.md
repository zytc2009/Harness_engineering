# Skill to Runtime Boundary Design

Date: 2026-04-11

> Scope: define a clean boundary between `skills/auto-dev` as the user-facing orchestrator and `harness-runtime` as the execution engine.

## Goal

Keep the architecture simple and strict:

- `auto-dev` skill is the entry point for requirement discussion
- `auto-dev` skill submits only normalized task documents
- `harness-runtime` consumes ready tasks, executes them, and owns execution state

This design avoids two common failure modes:

1. the skill and runtime both trying to interpret task intent
2. the skill and runtime both maintaining execution state

## Non-Goals

- turning `harness-runtime` CLI into the primary user interface
- moving execution logic back into the skill layer
- requiring the skill to fully design implementation details before enqueue

## Architecture

### Layer 1: `skills/auto-dev`

The skill has exactly two responsibilities:

1. discuss requirements with the user
2. create and enqueue a normalized task document

The skill is the front-end orchestration layer. It is allowed to ask follow-up questions when the user's request is still ambiguous. It is not allowed to become a second execution engine.

The skill may do the following:

- clarify vague user intent
- narrow scope
- confirm inputs, outputs, and acceptance criteria
- record explicit constraints
- write a task document
- hand the task document off to runtime

The skill must not do the following:

- maintain `running`, `failed`, `retry_count`, or other execution state
- secretly execute implementation work outside runtime
- reinterpret a task after it has already been handed off

### Language Independence

`auto-dev` should be language-agnostic.

The skill should not hardcode C++, Python, Go, or any other implementation language into its main control flow. Language is treated as task metadata, not as the identity of the skill.

This means:

- if the user specifies a language, the skill records it in `Constraints`
- if the user does not specify a language and it matters, the skill asks for clarification
- if the language is not important yet, the skill may leave it unspecified

`harness-cpp` is the first concrete harness example used to validate the end-to-end model. It is not a permanent dependency of the `auto-dev` skill design.

The long-term model is:

- `auto-dev` = language-neutral entry skill
- harness layer = language- or stack-specific execution constraints
- runtime = selects and applies the appropriate harness based on task metadata

### Layer 2: `harness-runtime`

`harness-runtime` is the back-end execution layer.

Its responsibilities are:

- validate task documents
- enqueue tasks
- execute queued tasks
- track task status, phase, retries, duration, and errors
- expose queue and worker status to other layers

The runtime must not:

- reopen requirement discussion with the user
- guess missing task intent
- override the task's objective or acceptance criteria

## Boundary Contract

The hand-off from skill to runtime happens through a task document.

The document is not "just markdown". It is the interface contract between the front-end orchestration layer and the execution engine.

### Contract Principle

The skill must not enqueue a task until the task is clear enough that runtime does not need to ask:

> "What exactly am I supposed to do?"

This does not mean the skill must decide all implementation details. It means the skill must remove ambiguity around the task objective and expected result.

## Skill Clarification Rules

The skill may enqueue a task only when all of the following are clear.

### Required fields

1. `Goal`
What problem is being solved, and what result is expected.

2. `Scope`
What is included in this task, and what is explicitly out of scope.

3. `Inputs`
What existing materials, files, repos, documents, or assumptions the runtime should rely on.

4. `Outputs`
What artifacts are expected from execution.

5. `Acceptance Criteria`
How completion will be judged.

6. `Constraints`
Hard constraints such as language, platform, dependency policy, forbidden paths, or harness flavor.

7. `Status`
Must be `ready` before enqueue.

### Clarification policy

If any required field is missing or ambiguous, the skill must ask follow-up questions before enqueue.

The skill should optimize for minimal questioning:

- ask only for missing information
- ask the smallest number of questions needed to make the task executable
- avoid implementation-level discussion unless the user asks for it

## Task Document Template

The first version should stay markdown-based but become stricter.

```md
# Task

## Goal
Implement ...

## Scope
- In scope: ...
- Out of scope: ...

## Inputs
- Existing repo: ...
- Reference docs: ...

## Outputs
- Modified code under ...
- Updated tests under ...
- Final completion summary

## Acceptance Criteria
- Existing behavior X remains unchanged
- New behavior Y works
- Relevant tests pass

## Constraints
- language: cpp
- platform: windows
- harness: harness-cpp
- dependency_policy: no-new-third-party-dependencies
- forbidden_paths: src/public_api/

## Status
ready
```

## Runtime Behavior

When runtime receives a task document via `--add-file`, it should:

1. validate required sections
2. reject incomplete or draft documents
3. normalize the document into a runtime task record
4. preserve the original source path for traceability
5. enqueue the task without changing its intent

The runtime may derive a short internal description for queue display, but it must not throw away the original source document reference.

## State Ownership

Execution state belongs to runtime.

### Skill-owned state

The skill may know:

- requirement conversation context
- the generated task document path
- whether enqueue succeeded or failed

The skill must not own:

- queue status
- current phase
- retry count
- final execution status

### Runtime-owned state

The runtime owns:

- `pending / running / done / failed / cancelled / skipped`
- `phase`
- `retry_count`
- `duration_s`
- `started_at / finished_at`
- `error`
- worker snapshot

If the skill later needs to report progress, it should read runtime state rather than rebuild its own copy.

## Runtime State Model

This design adopts a single task record model for runtime state.

Runtime state is split into:

- `task_queue.json`: the single source of truth for task lifecycle and execution fields
- `status.json`: the current worker snapshot only

`harness_tasks.json` is treated as legacy state and should be removed as runtime converges on this design.

This means the queue record owns both:

- scheduling fields such as `status`
- execution fields such as `phase`, `retry_count`, `duration_s`, and `error`

## Proposed Queue Record Shape

```json
{
  "id": "task-001",
  "source": "auto-dev",
  "source_type": "task_doc",
  "source_doc": "docs/tasks/task-001.md",
  "description": "Implement ...",
  "status": "pending",
  "phase": null,
  "retry_count": 0,
  "max_retries": 3,
  "created": "2026-04-11 12:00:00",
  "updated": "2026-04-11 12:00:00",
  "started_at": null,
  "finished_at": null,
  "duration_s": null,
  "error": null
}
```

This is intentionally execution-oriented. Requirement discussion state stays out of it.

## End-to-End Flow

1. user talks to `auto-dev`
2. `auto-dev` identifies missing task information
3. `auto-dev` asks follow-up questions until the task is executable
4. `auto-dev` writes a normalized task document
5. `auto-dev` submits it with:

```bash
python harness-runtime/main.py --add-file docs/tasks/task-001.md
```

6. `harness-runtime` validates and enqueues the task
7. `harness-runtime` later executes the task via `--drain` or another worker path
8. queue and execution state remain owned by runtime

## Design Consequences

### Benefits

- the user-facing skill stays simple
- runtime remains reusable as a batch engine
- task hand-off becomes auditable
- task ambiguity gets handled at the correct layer

### Tradeoffs

- the skill must become stricter about asking follow-up questions
- task documents become a real protocol artifact, not casual notes
- runtime cannot compensate for underspecified tasks by inventing intent

## Open Follow-Ups

1. add a canonical task template under `docs/tasks/`
2. decide whether `Constraints` should stay markdown-only or also be parsed into structured metadata
3. define how design artifacts from S1-S3 are referenced when they exist

## Decision

Adopt this boundary:

- `auto-dev` skill = requirement clarification + task creation + enqueue
- `harness-runtime` = validation + queueing + execution + execution state
- runtime state model = `task_queue.json` as the single task record source, `status.json` as worker snapshot, no long-term split with `harness_tasks.json`

This keeps the system composable and prevents the skill layer from collapsing into a second runtime.
