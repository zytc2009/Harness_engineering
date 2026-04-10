# Skill to Runtime Enqueue Plan

> Scope: connect requirement discussion output from `skills/auto-dev` to `harness-runtime` queue ingestion.

## Goal

Allow a requirement document discussed in the `auto-dev` skill to be submitted directly into `harness-runtime` as a queued task.

## Design

- requirement discussion remains in the skill layer
- runtime consumes only ready task documents
- runtime stores the source document path in queue/history metadata

## Deliverables

1. `harness-runtime` supports `--add-file <path>`
2. queue items persist:
   - `source_doc`
   - `source_type`
3. history records keep the same source metadata
4. `skills/auto-dev/SKILL.md` documents `--enqueue <task-doc>`

## Runtime Contract

Accepted task document requirements:

- markdown file
- contains `Goal`
- contains `Inputs`
- contains `Outputs`
- contains `Acceptance Criteria`
- contains `Status`
- `Status` must be `ready`

Runtime behavior:

- parse the task document into a normalized runtime description
- enqueue it as a normal pending task
- preserve `source_doc` for traceability
- reject draft or incomplete documents

## Follow-Up

Later work may add:

- a dedicated `docs/tasks/` template directory
- richer validation errors for malformed task documents
- direct skill-side command wrappers around `python harness-runtime/main.py --add-file ...`
