# Harness Contract

Date: 2026-04-11

> Scope: define the current filesystem and prompt-injection contract between `harness-runtime` and any concrete `harness-*` package.

## Goal

Allow `harness-runtime` to load language- or stack-specific execution guidance without hardcoding one concrete harness into runtime control flow.

This document describes the contract that is implemented now. It does not introduce a manifest format yet.

## Runtime Entry Point

Harness selection comes from task metadata:

```md
## Constraints
- harness: harness-cpp
```

If no `harness` constraint is present, runtime proceeds without harness-specific prompt context.

If a `harness` value is present, runtime treats it as the name of a harness directory under the repo root.

## Directory Contract

A harness must live at:

```text
<repo-root>/harness-<name>/
```

Example:

```text
harness-cpp/
```

The runtime currently recognizes harness directories by both:

- directory name starting with `harness-`
- presence of at least one standard context file

## Standard Context Files

These files are loaded into `Harness Context` when present:

- `HARNESS.md`
- `TASK_PROTOCOL.md`

These files are optional individually, but a harness directory must contain at least one of them to be recognized by the current registry.

## Phase Role Files

These files are loaded into `Harness Role Context` based on phase:

- `architect` -> `roles/architect.md`
- `implementer` -> `roles/implementer.md`
- `tester` -> `roles/test-engineer.md`

Current tester compatibility alias:

- `tester` -> `roles/tester.md`

If the phase-specific file is missing, runtime skips role-context injection for that phase.

## Minimum Practical Layout

```text
harness-foo/
  HARNESS.md
  TASK_PROTOCOL.md
  roles/
    architect.md
    implementer.md
    test-engineer.md
```

This is the recommended minimum layout for a fully usable harness.

## Runtime Behavior

When runtime builds the system prompt:

1. read task `Constraints`
2. resolve `constraints.harness`
3. load standard harness context files if the harness exists
4. load the current phase role file if it exists
5. inject those documents into the system prompt

Missing files are treated as absent context, not as fatal errors.

Unknown harness names are currently treated as "no harness context available".

## Design Intent

This contract keeps the boundary simple:

- `auto-dev` records harness choice as task metadata only
- `harness-runtime` owns harness discovery and prompt loading
- concrete harness packages own their local guidance docs

This prevents language-specific logic from being hardcoded into the entry skill.

## Non-Goals

This contract does not yet define:

- a manifest file such as `manifest.json` or `HARNESS.yaml`
- declared language/platform capability metadata
- required-vs-optional file validation rules
- harness-specific execution plugins beyond prompt-context loading

## Next Likely Extension

If harness count grows, the next extension should be an explicit manifest so runtime can validate:

- supported languages
- supported platforms
- available phases
- required documents
- compatibility/version metadata

That should be added only when the current directory-and-file convention becomes too implicit.
