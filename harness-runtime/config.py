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
    "kimi":     "https://api.kimi.com/coding/",
    "minimax":  "https://api.minimaxi.com/anthropic",
    "qwen":     "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm":      "https://open.bigmodel.cn/api/paas/v4",
    "xiaomi":   "https://api.xiaomimimo.com/v1",
    "ollama":   "http://localhost:11434/v1",
}


# ── Settings helpers ───────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _resolve_provider(phase: str | None = None) -> str:
    """Resolve provider, checking phase-specific override first.

    Phase override key: {PHASE.upper()}_PROVIDER (e.g. ARCHITECT_PROVIDER).
    Falls back to global PROVIDER, then "anthropic".
    """
    if phase:
        phase_val = os.environ.get(f"{phase.upper()}_PROVIDER", "").lower()
        if phase_val:
            return phase_val
    return os.environ.get("PROVIDER", "anthropic").lower()


def _resolve_base_url(provider: str, phase: str | None = None) -> str:
    """Resolve base URL with three-level precedence:

    1. {PHASE.upper()}_BASE_URL  (e.g. ARCHITECT_BASE_URL)
    2. OPENAI_COMPATIBLE_BASE_URL
    3. DEFAULT_BASE_URLS[provider]
    """
    if phase:
        phase_url = os.environ.get(f"{phase.upper()}_BASE_URL", "").strip()
        if phase_url:
            return phase_url
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


def _resolve_api_key(provider: str, phase: str | None = None) -> str:
    """Resolve API key, checking phase-specific override first.

    Phase override key: {PHASE.upper()}_API_KEY (e.g. ARCHITECT_API_KEY).
    Falls back to ANTHROPIC_API_KEY or OPENAI_COMPATIBLE_API_KEY.
    """
    if phase:
        phase_key = os.environ.get(f"{phase.upper()}_API_KEY", "").strip()
        if phase_key:
            return phase_key
    if provider == "anthropic":
        return get_setting("ANTHROPIC_API_KEY")
    return get_setting("OPENAI_COMPATIBLE_API_KEY", "not-needed")


_PHASE_DEFAULT_MAX_STEPS: dict[str, int] = {
    "architect":   10,
    "implementer": 25,
    "tester":      15,
}


def _resolve_phase_max_steps(phase: str) -> int:
    """Resolve max steps for a phase.

    Priority: {PHASE}_MAX_STEPS env var → _PHASE_DEFAULT_MAX_STEPS[phase].
    """
    val = os.environ.get(f"{phase.upper()}_MAX_STEPS", "").strip()
    if val.isdigit():
        return int(val)
    return _PHASE_DEFAULT_MAX_STEPS.get(phase, 15)


def _resolve_model(phase: str | None = None) -> str:
    """Resolve model name, checking phase-specific override first.

    Phase override key: {PHASE.upper()}_MODEL (e.g. ARCHITECT_MODEL).
    Falls back to MAIN_MODEL, then the default Claude model.
    """
    if phase:
        phase_model = os.environ.get(f"{phase.upper()}_MODEL", "").strip()
        if phase_model:
            return phase_model
    return get_setting("MAIN_MODEL", "claude-sonnet-4-20250514")


# ── LLM Factory ───────────────────────────────────────────────────

def get_llm(model: str | None = None, phase: str | None = None):
    """Build a LangChain LLM instance, optionally scoped to an agent phase.

    Per-phase env vars (all optional, fall back to global values):
      {PHASE}_PROVIDER   — e.g. ARCHITECT_PROVIDER=deepseek
      {PHASE}_MODEL      — e.g. ARCHITECT_MODEL=deepseek-reasoner
      {PHASE}_API_KEY    — e.g. ARCHITECT_API_KEY=sk-...
      {PHASE}_BASE_URL   — e.g. ARCHITECT_BASE_URL=https://...

    Args:
        model: Model name override. If None, resolved from env.
        phase: Agent phase ("architect" | "implementer" | "tester").

    Returns:
        LangChain BaseChatModel instance.
    """
    provider = _resolve_provider(phase)
    if model is None:
        model = _resolve_model(phase)
    api_key = _resolve_api_key(provider, phase)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=api_key)

    from langchain_openai import ChatOpenAI
    base_url = _resolve_base_url(provider, phase)
    user_agent = get_setting(f"{phase.upper()}_USER_AGENT") if phase else ""
    headers = {"User-Agent": user_agent} if user_agent else {}
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, default_headers=headers)


# ── Startup Validation ────────────────────────────────────────────

def _validate_phase(phase: str) -> None:
    """Validate config for a specific phase if it has a provider override."""
    phase_provider = os.environ.get(f"{phase.upper()}_PROVIDER", "").lower()
    if not phase_provider:
        return  # No override; global config covers it

    if phase_provider == "anthropic":
        key = get_setting(f"{phase.upper()}_API_KEY") or get_setting("ANTHROPIC_API_KEY")
        if not key:
            raise EnvironmentError(
                f"\n{phase.upper()}_PROVIDER=anthropic but no API key found.\n"
                f"Set {phase.upper()}_API_KEY or ANTHROPIC_API_KEY in .env\n"
            )
        return

    if phase_provider != "ollama":
        key = get_setting(f"{phase.upper()}_API_KEY") or get_setting("OPENAI_COMPATIBLE_API_KEY")
        if not key:
            raise EnvironmentError(
                f"\n{phase.upper()}_PROVIDER={phase_provider} but no API key found.\n"
                f"Set {phase.upper()}_API_KEY in .env\n"
            )

    _resolve_base_url(phase_provider, phase)  # raises if unknown provider


def validate():
    """Check required config at startup. Raises on missing values."""
    provider = _resolve_provider()

    if provider == "anthropic":
        if not get_setting("ANTHROPIC_API_KEY"):
            raise EnvironmentError(
                "\nANTHROPIC_API_KEY is not set.\n"
                "Edit .env: ANTHROPIC_API_KEY=your_key_here\n"
            )
    elif provider != "ollama" and not get_setting("OPENAI_COMPATIBLE_API_KEY"):
        raise EnvironmentError(
            f"\nOPENAI_COMPATIBLE_API_KEY is not set (provider={provider}).\n"
            f"Edit .env: OPENAI_COMPATIBLE_API_KEY=your_key_here\n"
        )
    else:
        _resolve_base_url(provider)  # raises if unknown + no override

    # Validate per-phase overrides
    for phase in ("architect", "implementer", "tester"):
        _validate_phase(phase)

    try:
        import langchain_openai  # noqa: F401
    except ImportError:
        raise ImportError(
            "\nlangchain-openai is not installed.\n"
            "Run: pip install langchain-openai\n"
        )
