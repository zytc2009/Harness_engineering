"""Task document parsing and normalization helpers."""

from __future__ import annotations

import re
from pathlib import Path

DOC_REQUIRED_SECTIONS = ("goal", "inputs", "outputs", "acceptance criteria", "status")


class TaskDocValidationError(ValueError):
    """Raised when a task document fails validation."""


def parse_task_doc_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    status_inline: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        inline_status = re.match(r"^\s*status\s*:\s*(.+?)\s*$", line, re.IGNORECASE)
        if inline_status:
            status_inline = inline_status.group(1).strip()
        if current is not None:
            sections[current].append(line)

    normalized = {
        key: "\n".join(value).strip()
        for key, value in sections.items()
        if "\n".join(value).strip()
    }
    if status_inline and "status" not in normalized:
        normalized["status"] = status_inline
    return normalized


def render_doc_task_description(sections: dict[str, str]) -> str:
    lines = [
        f"[Goal] {sections['goal']}",
        f"[Input] {sections['inputs']}",
        f"[Output] {sections['outputs']}",
        f"[Acceptance Criteria] {sections['acceptance criteria']}",
    ]
    if sections.get("scope"):
        lines.append(f"[Scope] {sections['scope']}")
    if sections.get("constraints"):
        lines.append(f"[Constraints] {sections['constraints']}")
    if sections.get("open questions"):
        lines.append(f"[Open Questions] {sections['open questions']}")
    return "\n".join(lines)


def parse_constraints(section_text: str) -> dict[str, str]:
    constraints: dict[str, str] = {}
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("-", "*")):
            line = line[1:].strip()
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()
        if key and value:
            constraints[key] = value
    return constraints


def validate_task_doc(doc_path: str | Path) -> tuple[Path, dict[str, str], dict[str, str]]:
    path = Path(doc_path).resolve()
    if not path.exists() or not path.is_file():
        raise TaskDocValidationError(f"Task document not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise TaskDocValidationError(f"Task document is empty: {path}")
    sections = parse_task_doc_sections(text)
    missing = [name for name in DOC_REQUIRED_SECTIONS if not sections.get(name)]
    if missing:
        raise TaskDocValidationError(f"Task document missing required sections: {', '.join(missing)}")
    if sections["status"].strip().lower() != "ready":
        raise TaskDocValidationError(
            f"Task document is not ready for enqueue (status '{sections['status'].strip()}'): {path}"
        )
    invalid_constraint_lines: list[str] = []
    for raw_line in sections.get("constraints", "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        candidate = line[1:].strip() if line.startswith(("-", "*")) else line
        key, sep, value = candidate.partition(":")
        if not sep or not key.strip() or not value.strip():
            invalid_constraint_lines.append(line)
    if invalid_constraint_lines:
        raise TaskDocValidationError(
            "Task document has invalid constraint lines: " + "; ".join(invalid_constraint_lines)
        )
    constraints = parse_constraints(sections.get("constraints", ""))
    return path, sections, constraints


def load_task_doc(doc_path: str | Path) -> tuple[Path, str, dict[str, str]]:
    path, sections, constraints = validate_task_doc(doc_path)
    return path, render_doc_task_description(sections), constraints
