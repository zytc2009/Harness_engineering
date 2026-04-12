"""Tests for unified provider/cli execution resolution."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

sys.path.insert(0, str(Path(__file__).parent.parent))

import execution


class TestResolvePhaseExecution:
    def test_defaults_to_provider(self, env_vars):
        env_vars(
            PROVIDER="deepseek",
            MAIN_MODEL="deepseek-chat",
            OPENAI_COMPATIBLE_API_KEY="k",
            ARCHITECT_PROVIDER="",
            ARCHITECT_MODEL="",
            ARCHITECT_API_KEY="",
        )
        resolved = execution.resolve_phase_execution("architect")
        assert resolved["mode"] == "provider"
        assert resolved["provider"] == "deepseek"
        assert resolved["model"] == "deepseek-chat"

    def test_uses_cli_mode_from_constraints(self, env_vars):
        env_vars(EXECUTION_MODE="provider", CLI_COMMAND="")
        resolved = execution.resolve_phase_execution(
            "implementer",
            task_metadata={
                "constraints": {
                    "execution_mode": "cli",
                    "cli_command": "codex exec -o {output_file} -",
                    "cli_timeout": "240",
                }
            },
        )
        assert resolved == {
            "mode": "cli",
            "command": "codex exec -o {output_file} -",
            "timeout": 240,
        }

    def test_phase_constraint_overrides_global(self, env_vars):
        env_vars(EXECUTION_MODE="provider", CLI_COMMAND="global -")
        resolved = execution.resolve_phase_execution(
            "tester",
            task_metadata={
                "constraints": {
                    "execution_mode": "cli",
                    "tester_cli_command": "tester-cmd -",
                }
            },
        )
        assert resolved["mode"] == "cli"
        assert resolved["command"] == "tester-cmd -"


class TestValidation:
    def test_cli_mode_requires_command(self, env_vars):
        env_vars(EXECUTION_MODE="cli", CLI_COMMAND="")
        with pytest.raises(EnvironmentError, match="no CLI command"):
            execution.validate_runtime()

    def test_cli_only_runtime_skips_langchain_openai_import(self, env_vars):
        env_vars(EXECUTION_MODE="cli", CLI_COMMAND="codex exec -o {output_file} -")
        execution.validate_runtime()

    def test_windows_cli_rejects_prompt_content(self, env_vars):
        env_vars(EXECUTION_MODE="cli", CLI_COMMAND="tool --prompt {prompt_content}")
        with patch.object(execution.sys, "platform", "win32"):
            with pytest.raises(EnvironmentError, match="cannot use \\{prompt_content\\} on Windows"):
                execution.validate_runtime()


class TestInvokePhase:
    def test_invoke_phase_cli_uses_subprocess(self, env_vars):
        env_vars(EXECUTION_MODE="cli", CLI_COMMAND="codex exec -")
        completed = MagicMock(returncode=0, stdout="cli output", stderr="")
        with patch("execution.subprocess.run", return_value=completed):
            result = execution.invoke_phase(
                "architect",
                [SystemMessage(content="sys"), HumanMessage(content="user")],
            )
        assert result == "cli output"

    def test_invoke_phase_provider_uses_config_llm(self, env_vars):
        env_vars(PROVIDER="anthropic", ANTHROPIC_API_KEY="key", MAIN_MODEL="claude-test")
        llm = MagicMock()
        llm.stream.return_value = []
        llm.invoke.return_value = MagicMock(content="provider output")
        with patch("execution.config.get_llm", return_value=llm) as mock_get_llm:
            result = execution.invoke_phase(
                "architect",
                [SystemMessage(content="sys"), HumanMessage(content="user")],
            )
        assert result == "provider output"
        assert mock_get_llm.called
