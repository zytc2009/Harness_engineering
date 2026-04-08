"""Tests for config module — provider routing and validation."""

import os
import sys
import pytest


@pytest.fixture(autouse=True)
def _reload_config():
    """Force reimport of config module for each test to pick up env changes."""
    mod_name = "config"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    yield
    if mod_name in sys.modules:
        del sys.modules[mod_name]


class TestResolveProvider:
    def test_default_is_anthropic(self, env_vars):
        os.environ.pop("PROVIDER", None)
        from config import _resolve_provider
        assert _resolve_provider() == "anthropic"

    def test_reads_env(self, env_vars):
        env_vars(PROVIDER="deepseek")
        from config import _resolve_provider
        assert _resolve_provider() == "deepseek"

    def test_case_insensitive(self, env_vars):
        env_vars(PROVIDER="DeepSeek")
        from config import _resolve_provider
        assert _resolve_provider() == "deepseek"


class TestDefaultBaseUrls:
    def test_contains_known_providers(self):
        from config import DEFAULT_BASE_URLS
        expected = {"openai", "deepseek", "kimi", "minimax", "qwen", "glm", "xiaomi", "ollama"}
        assert expected.issubset(set(DEFAULT_BASE_URLS.keys()))

    def test_ollama_points_to_localhost(self):
        from config import DEFAULT_BASE_URLS
        assert "localhost:11434" in DEFAULT_BASE_URLS["ollama"]


class TestResolveBaseUrl:
    def test_env_override_takes_priority(self, env_vars):
        env_vars(OPENAI_COMPATIBLE_BASE_URL="https://custom.api/v1")
        from config import _resolve_base_url
        assert _resolve_base_url("deepseek") == "https://custom.api/v1"

    def test_falls_back_to_default(self, env_vars):
        os.environ.pop("OPENAI_COMPATIBLE_BASE_URL", None)
        from config import _resolve_base_url
        url = _resolve_base_url("deepseek")
        assert "deepseek" in url

    def test_unknown_provider_raises(self, env_vars):
        os.environ.pop("OPENAI_COMPATIBLE_BASE_URL", None)
        from config import _resolve_base_url
        with pytest.raises(ValueError, match="Unknown provider"):
            _resolve_base_url("nonexistent_provider")


class TestResolveProviderPerPhase:
    def test_phase_override_takes_priority(self, env_vars):
        env_vars(PROVIDER="anthropic", ARCHITECT_PROVIDER="deepseek")
        from config import _resolve_provider
        assert _resolve_provider(phase="architect") == "deepseek"

    def test_falls_back_to_global_when_no_phase_override(self, env_vars):
        env_vars(PROVIDER="kimi")
        os.environ.pop("IMPLEMENTER_PROVIDER", None)
        from config import _resolve_provider
        assert _resolve_provider(phase="implementer") == "kimi"

    def test_no_phase_uses_global(self, env_vars):
        env_vars(PROVIDER="qwen")
        from config import _resolve_provider
        assert _resolve_provider() == "qwen"

    def test_phase_override_is_case_insensitive(self, env_vars):
        env_vars(TESTER_PROVIDER="DeepSeek")
        from config import _resolve_provider
        assert _resolve_provider(phase="tester") == "deepseek"

    def test_empty_phase_override_falls_back(self, env_vars):
        env_vars(PROVIDER="kimi", ARCHITECT_PROVIDER="")
        from config import _resolve_provider
        assert _resolve_provider(phase="architect") == "kimi"


class TestResolveBaseUrlPerPhase:
    def test_phase_base_url_takes_priority(self, env_vars):
        env_vars(ARCHITECT_BASE_URL="https://arch.api/v1")
        os.environ.pop("OPENAI_COMPATIBLE_BASE_URL", None)
        from config import _resolve_base_url
        assert _resolve_base_url("deepseek", phase="architect") == "https://arch.api/v1"

    def test_global_base_url_used_when_no_phase_override(self, env_vars):
        env_vars(OPENAI_COMPATIBLE_BASE_URL="https://global.api/v1")
        os.environ.pop("IMPLEMENTER_BASE_URL", None)
        from config import _resolve_base_url
        assert _resolve_base_url("deepseek", phase="implementer") == "https://global.api/v1"

    def test_falls_back_to_default_when_nothing_set(self, env_vars):
        os.environ.pop("TESTER_BASE_URL", None)
        os.environ.pop("OPENAI_COMPATIBLE_BASE_URL", None)
        from config import _resolve_base_url
        assert "deepseek" in _resolve_base_url("deepseek", phase="tester")

    def test_no_phase_still_works(self, env_vars):
        os.environ.pop("OPENAI_COMPATIBLE_BASE_URL", None)
        from config import _resolve_base_url
        assert "deepseek" in _resolve_base_url("deepseek")


class TestResolveModel:
    def test_phase_model_takes_priority(self, env_vars):
        env_vars(MAIN_MODEL="claude-opus-4-6", ARCHITECT_MODEL="deepseek-reasoner")
        from config import _resolve_model
        assert _resolve_model(phase="architect") == "deepseek-reasoner"

    def test_falls_back_to_main_model(self, env_vars):
        env_vars(MAIN_MODEL="claude-opus-4-6", IMPLEMENTER_MODEL="")
        from config import _resolve_model
        assert _resolve_model(phase="implementer") == "claude-opus-4-6"

    def test_no_phase_returns_main_model(self, env_vars):
        env_vars(MAIN_MODEL="claude-sonnet-4-6")
        from config import _resolve_model
        assert _resolve_model() == "claude-sonnet-4-6"


class TestResolveApiKey:
    def test_phase_api_key_takes_priority(self, env_vars):
        env_vars(ANTHROPIC_API_KEY="global-key", ARCHITECT_API_KEY="arch-key")
        from config import _resolve_api_key
        assert _resolve_api_key("anthropic", phase="architect") == "arch-key"

    def test_falls_back_to_global_anthropic_key(self, env_vars):
        env_vars(ANTHROPIC_API_KEY="global-key", IMPLEMENTER_API_KEY="")
        from config import _resolve_api_key
        assert _resolve_api_key("anthropic", phase="implementer") == "global-key"

    def test_falls_back_to_openai_compat_key(self, env_vars):
        env_vars(OPENAI_COMPATIBLE_API_KEY="compat-key", TESTER_API_KEY="")
        from config import _resolve_api_key
        assert _resolve_api_key("deepseek", phase="tester") == "compat-key"


class TestValidate:
    def test_anthropic_missing_key(self, env_vars):
        # Clear all phase overrides and global key to isolate the check
        env_vars(
            PROVIDER="anthropic", ANTHROPIC_API_KEY="",
            ARCHITECT_PROVIDER="", IMPLEMENTER_PROVIDER="", TESTER_PROVIDER="",
        )
        from config import validate
        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            validate()

    def test_openai_compat_missing_key(self, env_vars):
        env_vars(
            PROVIDER="deepseek", OPENAI_COMPATIBLE_API_KEY="",
            ARCHITECT_PROVIDER="", IMPLEMENTER_PROVIDER="", TESTER_PROVIDER="",
        )
        from config import validate
        with pytest.raises(EnvironmentError, match="OPENAI_COMPATIBLE_API_KEY"):
            validate()

    def test_ollama_skips_api_key_check(self, env_vars):
        env_vars(
            PROVIDER="ollama", OPENAI_COMPATIBLE_API_KEY="",
            ARCHITECT_PROVIDER="", IMPLEMENTER_PROVIDER="", TESTER_PROVIDER="",
        )
        from config import validate
        # Should not raise for missing API key
        validate()
