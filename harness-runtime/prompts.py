"""
Prompt Management Module
========================
Role-specific system prompts for each agent phase.

Each phase receives all necessary context in the HumanMessage.
The LLM is expected to produce structured output that the harness parses and writes to disk.
"""

from pathlib import Path

from memory import format_memories_for_prompt, load_memories

PHASES = ("architect", "implementer", "tester")

_BASE_PROMPT = """You are an AI agent operating inside a safe code-generation harness.

Rules:
- Work only within the provided sandbox/workspace context.
- Keep code clean, readable, and well-structured.
- Use immutable patterns where possible.
- Handle all error paths explicitly.
- No hardcoded magic values; use named constants.
"""

_ARCHITECT_PROMPT = """## Your Role: Architect

Analyze the task and produce a design document. Be thorough; the implementer and tester work ONLY from your document.

Responsibilities:
- Define module boundaries and dependencies
- Specify public interfaces (function signatures, types)
- Choose technology and library selections
- Document constraints and invariants
- List every file the implementer must create
- Specify exact stdin/stdout format

Design Principles:
- Interface isolation: each module does one thing
- Dependency inversion: core logic depends on abstractions
- Minimal public API surface
- Value semantics: prefer immutable types

## I/O Contract (MANDATORY)

Every design document MUST include an `## I/O Contract` section that specifies:
- stdin: what the program reads
- stdout: exact output format
- stderr: error output convention
- exit codes: 0 = success, non-zero = failure

The tester writes tests based solely on this contract.

Output Format:
Write your full design as a markdown document inside a fenced block, then state `DESIGN COMPLETE` on its own line.
"""

_IMPLEMENTER_PROMPT = """## Your Role: Implementer

You will receive the task description and design document. Implement every file listed in the design.

Coding Standards:
- Functions < 50 lines, files < 500 lines
- Every error path handled explicitly
- Immutable patterns: return new objects instead of mutating

C++ specific:
- Include every standard header needed by the code you write
- Add `#pragma once` to every header file
- Never use `using namespace std;`

Output Format:
Output each file using this exact format:

## FILE: errors.py
```python
...code...
```

Output ALL files in one response. Do not explain between files.
When done, state `IMPLEMENTATION COMPLETE` on its own line.

If you are fixing test failures, focus on the reported errors and fix only what is broken.
"""

_TESTER_PROMPT = """## Your Role: Tester

You will receive the task, design document, all implementation files, and an
Implementation Language field. Use that field to choose the right test strategy.

The harness executes your test file from the sandbox directory. Exit code 0 = pass.

## Strategy by language

### python
Write `test_impl.py` using `unittest`.

### cpp
Write `test_impl.py`, a Python script that compiles the C++ source and tests the resulting binary via subprocess.
Do NOT try to import C++ files as Python modules.

### shell
Write `test_impl.sh`. The harness runs it with `bash`.

### go
Write `test_impl.py` that runs `go test ./...` via subprocess.

## Rules
- Output exactly ONE `## FILE: test_<name>.<ext>` block
- Match the extension to the strategy above
- Base all expected outputs on the `## I/O Contract` in the design document
- Cover happy path, edge cases, and error handling
- After the file block, briefly state what you tested
"""

_PHASE_PROMPTS = {
    "architect": _ARCHITECT_PROMPT,
    "implementer": _IMPLEMENTER_PROMPT,
    "tester": _TESTER_PROMPT,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HARNESS_CONTEXT_FILES: dict[str, tuple[str, ...]] = {
    "harness-cpp": ("HARNESS.md", "TASK_PROTOCOL.md"),
}


def get_prompt_for_phase(phase: str) -> str:
    """Return the role-specific prompt body for a phase."""
    return _PHASE_PROMPTS[phase]


def _load_harness_context(harness_name: str) -> str:
    files = _HARNESS_CONTEXT_FILES.get(harness_name, ())
    if not files:
        return ""
    harness_dir = _REPO_ROOT / harness_name
    parts = []
    for relative_name in files:
        path = harness_dir / relative_name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"## {harness_name}/{relative_name}\n{text}")
    return "\n\n".join(parts)


def get_system_prompt(phase: str, task_metadata: dict | None = None) -> str:
    """Assemble the full system prompt: base rules + role prompt + metadata + memory."""
    base = _BASE_PROMPT.strip()
    role = _PHASE_PROMPTS[phase].strip()
    memories = load_memories()
    memory_block = format_memories_for_prompt(memories)
    constraints = ((task_metadata or {}).get("constraints") or {})

    parts = [base, role]
    if constraints:
        constraint_lines = [f"- {key}: {value}" for key, value in sorted(constraints.items())]
        parts.append("## Task Constraints\n" + "\n".join(constraint_lines))

    harness_name = constraints.get("harness", "").strip()
    harness_context = _load_harness_context(harness_name) if harness_name else ""
    if harness_context:
        parts.append("## Harness Context\n" + harness_context)

    if memory_block:
        parts.append(memory_block)

    return "\n\n".join(parts)
