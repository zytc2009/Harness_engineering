"""Tests for prompts module — role-specific system prompts."""

import pytest
from prompts import get_prompt_for_phase, PHASES, get_system_prompt


class TestGetPromptForPhase:
    def test_architect_prompt_mentions_design(self):
        prompt = get_prompt_for_phase("architect")
        assert "design" in prompt.lower()

    def test_implementer_prompt_mentions_code(self):
        prompt = get_prompt_for_phase("implementer")
        assert "implement" in prompt.lower() or "code" in prompt.lower()

    def test_tester_prompt_mentions_test(self):
        prompt = get_prompt_for_phase("tester")
        assert "test" in prompt.lower()

    def test_unknown_phase_raises(self):
        with pytest.raises(KeyError):
            get_prompt_for_phase("unknown_phase")

    def test_all_phases_have_prompts(self):
        for phase in PHASES:
            prompt = get_prompt_for_phase(phase)
            assert len(prompt) > 50


class TestGetSystemPrompt:
    def test_includes_base_rules(self):
        prompt = get_system_prompt("architect")
        assert "sandbox" in prompt.lower() or "workspace" in prompt.lower()

    def test_includes_phase_prompt(self):
        prompt = get_system_prompt("architect")
        assert "design" in prompt.lower()

    def test_includes_memory_when_present(self, monkeypatch):
        monkeypatch.setattr(
            "prompts.load_memories",
            lambda: [{"date": "2026-04-07", "summary": "built auth module"}],
        )
        prompt = get_system_prompt("implementer")
        assert "auth module" in prompt

    def test_includes_task_constraints_when_present(self):
        prompt = get_system_prompt(
            "architect",
            task_metadata={"constraints": {"language": "cpp", "platform": "windows"}},
        )
        assert "Task Constraints" in prompt
        assert "- language: cpp" in prompt
        assert "- platform: windows" in prompt

    def test_includes_harness_context_when_present(self, monkeypatch):
        monkeypatch.setattr(
            "prompts.load_harness_context",
            lambda harness_name: "## harness-cpp/HARNESS.md\nC++20 only" if harness_name == "harness-cpp" else "",
        )
        prompt = get_system_prompt(
            "implementer",
            task_metadata={"constraints": {"harness": "harness-cpp"}},
        )
        assert "Harness Context" in prompt
        assert "C++20 only" in prompt

    def test_includes_phase_specific_role_context_when_present(self, monkeypatch):
        monkeypatch.setattr(
            "prompts.load_harness_role_context",
            lambda harness_name, phase: "## harness-cpp/roles/implementer.md\nRAII only"
            if harness_name == "harness-cpp" and phase == "implementer"
            else "",
        )
        prompt = get_system_prompt(
            "implementer",
            task_metadata={"constraints": {"harness": "harness-cpp"}},
        )
        assert "Harness Role Context" in prompt
        assert "RAII only" in prompt
