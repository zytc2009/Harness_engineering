"""Tests for harness discovery and context loading."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness_registry import (
    get_harness_spec,
    list_harnesses,
    load_harness_context,
    load_harness_role_context,
)


class TestHarnessRegistry:
    def test_get_harness_spec_returns_known_harness(self):
        spec = get_harness_spec("harness-cpp")
        assert spec is not None
        assert spec.name == "harness-cpp"
        assert spec.root.name == "harness-cpp"

    def test_get_harness_spec_rejects_unknown_harness(self):
        assert get_harness_spec("harness-missing") is None

    def test_list_harnesses_includes_cpp(self):
        names = [spec.name for spec in list_harnesses()]
        assert "harness-cpp" in names

    def test_load_harness_context_reads_standard_files(self):
        context = load_harness_context("harness-cpp")
        assert "harness-cpp/HARNESS.md" in context
        assert "harness-cpp/TASK_PROTOCOL.md" in context

    def test_load_harness_role_context_reads_phase_file(self):
        context = load_harness_role_context("harness-cpp", "implementer")
        assert "harness-cpp/roles/implementer.md" in context

    def test_load_harness_role_context_supports_tester_alias(self):
        context = load_harness_role_context("harness-cpp", "tester")
        assert "harness-cpp/roles/test-engineer.md" in context
