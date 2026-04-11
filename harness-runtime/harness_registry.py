"""Harness discovery and context loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HARNESS_DIR_PREFIX = "harness-"
_CONTEXT_FILES = ("HARNESS.md", "TASK_PROTOCOL.md")
_ROLE_FILE_CANDIDATES = {
    "architect": ("roles/architect.md",),
    "implementer": ("roles/implementer.md",),
    "tester": ("roles/test-engineer.md", "roles/tester.md"),
}


@dataclass(frozen=True)
class HarnessSpec:
    name: str
    root: Path


def get_harness_spec(harness_name: str) -> HarnessSpec | None:
    normalized = harness_name.strip()
    if not normalized or not normalized.startswith(_HARNESS_DIR_PREFIX):
        return None
    root = _REPO_ROOT / normalized
    if not root.is_dir():
        return None
    if not any((root / relative_name).exists() for relative_name in _CONTEXT_FILES):
        return None
    return HarnessSpec(name=normalized, root=root)


def list_harnesses() -> list[HarnessSpec]:
    specs: list[HarnessSpec] = []
    for child in sorted(_REPO_ROOT.iterdir()):
        if not child.is_dir() or not child.name.startswith(_HARNESS_DIR_PREFIX):
            continue
        spec = get_harness_spec(child.name)
        if spec is not None:
            specs.append(spec)
    return specs


def load_harness_context(harness_name: str) -> str:
    spec = get_harness_spec(harness_name)
    if spec is None:
        return ""
    parts: list[str] = []
    for relative_name in _CONTEXT_FILES:
        path = spec.root / relative_name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"## {spec.name}/{relative_name}\n{text}")
    return "\n\n".join(parts)


def load_harness_role_context(harness_name: str, phase: str) -> str:
    spec = get_harness_spec(harness_name)
    if spec is None:
        return ""
    for relative_name in _ROLE_FILE_CANDIDATES.get(phase, ()):
        path = spec.root / relative_name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return f"## {spec.name}/{relative_name}\n{text}"
    return ""
