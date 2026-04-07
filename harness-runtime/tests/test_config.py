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


class TestValidate:
    def test_anthropic_missing_key(self, env_vars):
        env_vars(PROVIDER="anthropic")
        os.environ.pop("ANTHROPIC_API_KEY", None)
        from config import validate
        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            validate()

    def test_openai_compat_missing_key(self, env_vars):
        env_vars(PROVIDER="deepseek")
        os.environ.pop("OPENAI_COMPATIBLE_API_KEY", None)
        from config import validate
        with pytest.raises(EnvironmentError, match="OPENAI_COMPATIBLE_API_KEY"):
            validate()

    def test_ollama_skips_api_key_check(self, env_vars):
        env_vars(PROVIDER="ollama")
        os.environ.pop("OPENAI_COMPATIBLE_API_KEY", None)
        from config import validate
        # Should not raise for missing API key
        validate()
