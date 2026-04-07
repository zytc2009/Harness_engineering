"""
Config Module — Multi-Provider LLM Factory
===========================================
Reads .env, resolves provider settings, and builds LangChain LLM instances.

Supported providers:
  anthropic  -> ChatAnthropic
  openai, deepseek, kimi, qwen, glm, minimax, xiaomi, ollama, custom
             -> ChatOpenAI + provider-specific base_url

Usage:
  from config import get_llm, get_setting
  llm = get_llm(get_setting("MAIN_MODEL"))
"""

import os
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key not in os.environ:
                os.environ[key] = value

# ── Default base URLs for OpenAI-compatible providers ──────────────

DEFAULT_BASE_URLS: dict[str, str] = {
    "openai":   "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "kimi":     "https://api.moonshot.cn/v1",
    "minimax":  "https://api.minimax.chat/v1",
    "qwen":     "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm":      "https://open.bigmodel.cn/api/paas/v4",
    "xiaomi":   "https://api.xiaomimimo.com/v1",
    "ollama":   "http://localhost:11434/v1",
}


# ── Settings helpers ───────────────────────────────────────────────

def _resolve_provider() -> str:
    return os.environ.get("PROVIDER", "anthropic").lower()


def _resolve_base_url(provider: str) -> str:
    explicit = os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "").strip()
    if explicit:
        return explicit
    url = DEFAULT_BASE_URLS.get(provider, "")
    if not url:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Set OPENAI_COMPATIBLE_BASE_URL in .env, "
            f"or use one of: {sorted(DEFAULT_BASE_URLS.keys())}"
        )
    return url


def get_setting(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ── LLM Factory ───────────────────────────────────────────────────

def get_llm(model: str | None = None):
    """Build a LangChain LLM instance based on PROVIDER env var.

    Args:
        model: Model name. Defaults to MAIN_MODEL from env.

    Returns:
        LangChain BaseChatModel instance.
    """
    provider = _resolve_provider()
    if model is None:
        model = get_setting("MAIN_MODEL", "claude-sonnet-4-20250514")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=get_setting("ANTHROPIC_API_KEY"),
        )

    from langchain_openai import ChatOpenAI
    base_url = _resolve_base_url(provider)
    api_key = get_setting("OPENAI_COMPATIBLE_API_KEY", "not-needed")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


# ── Startup Validation ────────────────────────────────────────────

def validate():
    """Check required config at startup. Raises on missing values."""
    provider = _resolve_provider()

    if provider == "anthropic":
        if not get_setting("ANTHROPIC_API_KEY"):
            raise EnvironmentError(
                "\nANTHROPIC_API_KEY is not set.\n"
                "Edit .env: ANTHROPIC_API_KEY=your_key_here\n"
            )
        return

    # Ollama doesn't need a real API key
    if provider != "ollama" and not get_setting("OPENAI_COMPATIBLE_API_KEY"):
        raise EnvironmentError(
            f"\nOPENAI_COMPATIBLE_API_KEY is not set (provider={provider}).\n"
            f"Edit .env: OPENAI_COMPATIBLE_API_KEY=your_key_here\n"
        )

    _resolve_base_url(provider)  # raises if unknown + no override

    try:
        import langchain_openai  # noqa: F401
    except ImportError:
        raise ImportError(
            "\nlangchain-openai is not installed.\n"
            "Run: pip install langchain-openai\n"
        )
