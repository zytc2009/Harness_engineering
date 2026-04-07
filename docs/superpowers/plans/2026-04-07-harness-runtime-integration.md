# Harness Runtime Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate microharness's runtime engine into Harness_engineering, creating a multi-provider, multi-agent Python harness that implements the architect-implementer-tester self-healing loop.

**Architecture:** Port microharness's 6-layer architecture (config/guard/memory/tools/prompts/harness) as foundation, then extend the single-agent LangGraph state machine into a multi-agent orchestrator with phase routing (architect -> implementer -> tester -> retry loop). Each agent role uses phase-specific system prompts derived from existing `harness-cpp/roles/` definitions.

**Tech Stack:** Python 3.11+, LangGraph, LangChain (anthropic + openai), pytest

---

## File Structure

```
harness-runtime/
├── .env.example          # All provider configuration templates
├── requirements.txt      # Python dependencies
├── config.py             # Multi-provider LLM factory (10 providers + Ollama)
├── guard.py              # 3-tier tool safety guard
├── memory.py             # Cross-session persistence (memory.json)
├── tools.py              # Sandboxed file + code execution tools
├── prompts.py            # Role-specific system prompts (architect/implementer/tester)
├── orchestrator.py       # Multi-agent LangGraph state machine
├── main.py               # CLI entry point
└── tests/
    ├── __init__.py
    ├── conftest.py        # Shared pytest fixtures
    ├── test_config.py     # Provider routing tests
    ├── test_guard.py      # Safety classification tests
    ├── test_memory.py     # Persistence tests
    ├── test_tools.py      # Tool safety tests
    ├── test_prompts.py    # Prompt generation tests
    └── test_orchestrator.py  # State machine transition tests
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `harness-runtime/requirements.txt`
- Create: `harness-runtime/.env.example`
- Create: `harness-runtime/tests/__init__.py`
- Create: `harness-runtime/tests/conftest.py`

- [ ] **Step 1: Create `requirements.txt`**

```
# Core
langgraph>=0.2.0
langchain-core>=0.3.0
langchain-anthropic>=0.3.0
typing_extensions>=4.0.0

# OpenAI-compatible providers (DeepSeek, Kimi, Qwen, GLM, Ollama, etc.)
langchain-openai>=0.3.0

# Testing
pytest>=8.0.0
pytest-cov>=5.0.0
```

- [ ] **Step 2: Create `.env.example`**

```bash
# ═══════════════════════════════════════════════════
# MicroHarness Multi-Provider Configuration
# Copy to .env and fill in your values
# ═══════════════════════════════════════════════════

# ── Provider Selection ─────────────────────────────
# Options: anthropic, openai, deepseek, kimi, qwen, glm, minimax, xiaomi, ollama, custom
PROVIDER=anthropic

# ── Anthropic (PROVIDER=anthropic) ─────────────────
ANTHROPIC_API_KEY=your_key_here
MAIN_MODEL=claude-sonnet-4-20250514
MEMORY_MODEL=claude-haiku-4-5-20251001

# ── OpenAI-Compatible Providers ────────────────────
# Used for: openai, deepseek, kimi, qwen, glm, minimax, xiaomi, ollama, custom
# OPENAI_COMPATIBLE_API_KEY=your_key_here
# MAIN_MODEL=deepseek-chat
# MEMORY_MODEL=deepseek-chat

# ── Ollama (local models) ─────────────────────────
# PROVIDER=ollama
# MAIN_MODEL=gemma4:26b-a4b-it-q4_K_M
# MEMORY_MODEL=gemma4:26b-a4b-it-q4_K_M
# OPENAI_COMPATIBLE_API_KEY=ollama
# OPENAI_COMPATIBLE_BASE_URL=http://localhost:11434/v1

# ── Custom Provider (any OpenAI-compatible API) ───
# PROVIDER=custom
# OPENAI_COMPATIBLE_BASE_URL=https://your-api-endpoint/v1
# OPENAI_COMPATIBLE_API_KEY=your_key_here
# MAIN_MODEL=your-model-name
# MEMORY_MODEL=your-model-name

# ── Harness Settings ──────────────────────────────
MAX_STEPS=15
MAX_RETRIES=3
```

- [ ] **Step 3: Create `tests/__init__.py` and `tests/conftest.py`**

`tests/__init__.py` is empty.

`tests/conftest.py`:

```python
"""Shared fixtures for harness-runtime tests."""

import json
import os
import tempfile

import pytest


@pytest.fixture
def sandbox_dir(tmp_path):
    """Provides a temporary sandbox directory for tool tests."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    return str(sandbox)


@pytest.fixture
def memory_file(tmp_path):
    """Provides a temporary memory.json path."""
    return str(tmp_path / "memory.json")


@pytest.fixture
def env_vars():
    """Context manager to temporarily set environment variables."""
    original = {}

    def _set(**kwargs):
        for key, value in kwargs.items():
            original[key] = os.environ.get(key)
            os.environ[key] = value

    yield _set

    for key, orig_value in original.items():
        if orig_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_value
```

- [ ] **Step 4: Commit**

```bash
cd harness-runtime
git add requirements.txt .env.example tests/__init__.py tests/conftest.py
git commit -m "chore: scaffold harness-runtime project structure"
```

---

### Task 2: Config Module (Multi-Provider LLM Factory)

**Files:**
- Create: `harness-runtime/config.py`
- Create: `harness-runtime/tests/test_config.py`

- [ ] **Step 1: Write failing tests for config**

`tests/test_config.py`:

```python
"""Tests for config module — provider routing and validation."""

import os
import pytest


def test_default_provider_is_anthropic():
    """PROVIDER defaults to 'anthropic' when not set."""
    os.environ.pop("PROVIDER", None)
    from config import _resolve_provider
    assert _resolve_provider() == "anthropic"


def test_resolve_provider_reads_env(env_vars):
    """PROVIDER env var is respected."""
    env_vars(PROVIDER="deepseek")
    from config import _resolve_provider
    assert _resolve_provider() == "deepseek"


def test_default_base_urls_contains_known_providers():
    """All documented providers have default base URLs."""
    from config import DEFAULT_BASE_URLS
    expected = {"openai", "deepseek", "kimi", "minimax", "qwen", "glm", "xiaomi", "ollama"}
    assert expected.issubset(set(DEFAULT_BASE_URLS.keys()))


def test_ollama_default_base_url():
    """Ollama default points to localhost:11434."""
    from config import DEFAULT_BASE_URLS
    assert "localhost:11434" in DEFAULT_BASE_URLS["ollama"]


def test_resolve_base_url_uses_env_override(env_vars):
    """Explicit OPENAI_COMPATIBLE_BASE_URL overrides defaults."""
    env_vars(OPENAI_COMPATIBLE_BASE_URL="https://custom.api/v1")
    from config import _resolve_base_url
    assert _resolve_base_url("deepseek") == "https://custom.api/v1"


def test_resolve_base_url_falls_back_to_default():
    """When no env override, uses built-in default for known providers."""
    os.environ.pop("OPENAI_COMPATIBLE_BASE_URL", None)
    from config import _resolve_base_url
    url = _resolve_base_url("deepseek")
    assert "deepseek" in url


def test_resolve_base_url_unknown_provider_no_override():
    """Unknown provider with no override raises ValueError."""
    os.environ.pop("OPENAI_COMPATIBLE_BASE_URL", None)
    from config import _resolve_base_url
    with pytest.raises(ValueError, match="Unknown provider"):
        _resolve_base_url("nonexistent_provider")


def test_validate_anthropic_missing_key(env_vars):
    """Anthropic provider without API key raises EnvironmentError."""
    env_vars(PROVIDER="anthropic")
    os.environ.pop("ANTHROPIC_API_KEY", None)
    from config import validate
    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        validate()


def test_validate_openai_compat_missing_key(env_vars):
    """Non-anthropic provider without API key raises EnvironmentError."""
    env_vars(PROVIDER="deepseek")
    os.environ.pop("OPENAI_COMPATIBLE_API_KEY", None)
    from config import validate
    with pytest.raises(EnvironmentError, match="OPENAI_COMPATIBLE_API_KEY"):
        validate()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd harness-runtime
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `config` module does not exist yet.

- [ ] **Step 3: Implement `config.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd harness-runtime
python -m pytest tests/test_config.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add multi-provider config module with 10 provider support"
```

---

### Task 3: Guard Module (3-Tier Tool Safety)

**Files:**
- Create: `harness-runtime/guard.py`
- Create: `harness-runtime/tests/test_guard.py`

- [ ] **Step 1: Write failing tests for guard**

`tests/test_guard.py`:

```python
"""Tests for guard module — 3-tier safety classification."""

import pytest
from guard import (
    AUTO_APPROVE_TOOLS,
    ALWAYS_CONFIRM_TOOLS,
    DANGEROUS_KEYWORDS,
    is_dangerous,
    classify_tool,
)


class TestClassifyTool:
    def test_read_tools_are_auto_approve(self):
        assert classify_tool("list_files", {}) == "auto_approve"
        assert classify_tool("read_file", {"filename": "x.py"}) == "auto_approve"
        assert classify_tool("get_file_info", {"filename": "x.py"}) == "auto_approve"

    def test_write_tools_are_always_confirm(self):
        assert classify_tool("write_file", {"filename": "x.py", "content": "hi"}) == "always_confirm"
        assert classify_tool("delete_file", {"filename": "x.py"}) == "always_confirm"

    def test_unknown_tool_safe_content_is_auto_approve(self):
        assert classify_tool("run_python", {"filename": "hello.py"}) == "auto_approve"

    def test_unknown_tool_dangerous_content_is_keyword_check(self):
        assert classify_tool("run_python", {"filename": "rm -rf /"}) == "keyword_check"


class TestIsDangerous:
    def test_safe_content(self):
        assert is_dangerous({"filename": "main.py"}) is False

    def test_rm_command(self):
        assert is_dangerous({"cmd": "rm -rf /tmp"}) is True

    def test_shutil_rmtree(self):
        assert is_dangerous({"content": "import shutil; shutil.rmtree('/')"}) is True

    def test_drop_table(self):
        assert is_dangerous({"query": "DROP TABLE users"}) is True

    def test_case_insensitive(self):
        assert is_dangerous({"query": "drop table USERS"}) is True


class TestToolSets:
    def test_auto_approve_tools_are_read_only(self):
        for tool_name in AUTO_APPROVE_TOOLS:
            assert "write" not in tool_name.lower()
            assert "delete" not in tool_name.lower()
            assert "run" not in tool_name.lower()

    def test_no_overlap_between_auto_and_confirm(self):
        assert AUTO_APPROVE_TOOLS.isdisjoint(ALWAYS_CONFIRM_TOOLS)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_guard.py -v
```

Expected: FAIL — `guard` module does not exist yet.

- [ ] **Step 3: Implement `guard.py`**

```python
"""
Safety Guard Module
===================
3-tier tool safety classification and human confirmation.

Levels:
  AUTO_APPROVE   : Read-only tools, no side effects -> pass through
  ALWAYS_CONFIRM : Write/delete tools -> always ask human
  KEYWORD_CHECK  : Other tools -> check args for dangerous patterns
"""

DANGEROUS_KEYWORDS = [
    "rm ",
    "rm\t",
    "shutil.rmtree",
    "os.remove",
    "os.unlink",
    "DROP TABLE",
    "DELETE FROM",
    "format(",
    "subprocess.call",
    "> /dev/",
    "os.system(",
]

ALWAYS_CONFIRM_TOOLS: frozenset[str] = frozenset({
    "write_file",
    "delete_file",
})

AUTO_APPROVE_TOOLS: frozenset[str] = frozenset({
    "list_files",
    "read_file",
    "get_file_info",
})


def is_dangerous(tool_input: dict) -> bool:
    """Check if tool arguments contain dangerous keywords."""
    content = str(tool_input).lower()
    return any(kw.lower() in content for kw in DANGEROUS_KEYWORDS)


def classify_tool(tool_name: str, tool_input: dict) -> str:
    """Classify a tool call into one of three safety tiers.

    Returns:
        "auto_approve" | "always_confirm" | "keyword_check"
    """
    if tool_name in AUTO_APPROVE_TOOLS:
        return "auto_approve"
    if tool_name in ALWAYS_CONFIRM_TOOLS:
        return "always_confirm"
    if is_dangerous(tool_input):
        return "keyword_check"
    return "auto_approve"


def should_confirm(tool_name: str, tool_input: dict) -> bool:
    """Whether this tool call requires human confirmation."""
    level = classify_tool(tool_name, tool_input)
    return level in ("always_confirm", "keyword_check")


def request_human_approval(tool_name: str, tool_input: dict) -> bool:
    """Pause execution and ask the human operator for approval.

    Returns:
        True if approved, False if rejected.
    """
    level = classify_tool(tool_name, tool_input)
    if level == "always_confirm" and tool_name == "delete_file":
        flag = "DELETE OP"
    elif level == "keyword_check":
        flag = "HIGH RISK"
    else:
        flag = "WRITE OP"

    print(f"\n{'=' * 55}")
    print(f"  [HARNESS GUARD] {flag}")
    print(f"  Tool   : {tool_name}")
    for k, v in tool_input.items():
        display = str(v)
        if len(display) > 200:
            display = display[:200] + "... (truncated)"
        print(f"  {k:8}: {display}")
    print(f"{'=' * 55}")

    while True:
        answer = input("  Approve? (yes / no): ").strip().lower()
        if answer in ("yes", "y"):
            print("  Approved.\n")
            return True
        if answer in ("no", "n"):
            print("  Rejected. Operation cancelled.\n")
            return False
        print("  Please type 'yes' or 'no'.")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_guard.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add guard.py tests/test_guard.py
git commit -m "feat: add 3-tier tool safety guard module"
```

---

### Task 4: Memory Module (Cross-Session Persistence)

**Files:**
- Create: `harness-runtime/memory.py`
- Create: `harness-runtime/tests/test_memory.py`

- [ ] **Step 1: Write failing tests for memory**

`tests/test_memory.py`:

```python
"""Tests for memory module — cross-session persistence."""

import json
import pytest
from memory import load_memories, save_memories, format_memories_for_prompt, MAX_MEMORIES


class TestLoadMemories:
    def test_returns_empty_list_when_file_missing(self, memory_file):
        result = load_memories(memory_file)
        assert result == []

    def test_returns_empty_list_on_corrupt_json(self, memory_file):
        with open(memory_file, "w") as f:
            f.write("not json {{{")
        result = load_memories(memory_file)
        assert result == []

    def test_loads_valid_memories(self, memory_file):
        data = [{"date": "2026-04-07", "task": "test", "summary": "did a thing"}]
        with open(memory_file, "w") as f:
            json.dump(data, f)
        result = load_memories(memory_file)
        assert len(result) == 1
        assert result[0]["summary"] == "did a thing"


class TestSaveMemories:
    def test_saves_and_reloads(self, memory_file):
        records = [{"date": "2026-04-07", "task": "t1", "summary": "s1"}]
        save_memories(records, memory_file)
        loaded = load_memories(memory_file)
        assert loaded == records

    def test_trims_to_max_memories(self, memory_file):
        records = [
            {"date": f"2026-04-{i:02d}", "task": f"t{i}", "summary": f"s{i}"}
            for i in range(MAX_MEMORIES + 10)
        ]
        save_memories(records, memory_file)
        loaded = load_memories(memory_file)
        assert len(loaded) == MAX_MEMORIES
        assert loaded[-1]["summary"] == records[-1]["summary"]


class TestFormatMemories:
    def test_empty_returns_empty_string(self):
        assert format_memories_for_prompt([]) == ""

    def test_formats_last_five(self):
        records = [
            {"date": f"2026-04-{i:02d}", "summary": f"summary {i}"}
            for i in range(10)
        ]
        result = format_memories_for_prompt(records)
        assert "summary 5" in result
        assert "summary 9" in result
        assert "summary 0" not in result

    def test_includes_header(self):
        records = [{"date": "2026-04-07", "summary": "test"}]
        result = format_memories_for_prompt(records)
        assert "Long-Term Memory" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_memory.py -v
```

Expected: FAIL — `memory` module does not exist yet.

- [ ] **Step 3: Implement `memory.py`**

```python
"""
Long-Term Memory Module
=======================
Cross-session persistence. Saves session summaries to JSON.

Flow:
  Session ends -> LLM extracts summary -> append to memory.json
  Next startup -> load memory.json -> inject into system prompt
"""

import json
import os
from datetime import datetime
from pathlib import Path

MAX_MEMORIES = 20

_DEFAULT_MEMORY_FILE = str(Path(__file__).parent / "memory.json")


def load_memories(path: str = _DEFAULT_MEMORY_FILE) -> list[dict]:
    """Load persisted memories. Returns [] if file missing or corrupt."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_memories(memories: list[dict], path: str = _DEFAULT_MEMORY_FILE) -> None:
    """Persist memories to JSON. Trims oldest if over MAX_MEMORIES."""
    trimmed = memories[-MAX_MEMORIES:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def format_memories_for_prompt(memories: list[dict]) -> str:
    """Format last 5 memories as a block for system prompt injection."""
    if not memories:
        return ""
    lines = ["## Long-Term Memory (from previous sessions)\n"]
    for m in memories[-5:]:
        lines.append(f"- [{m['date']}] {m['summary']}")
    return "\n".join(lines)


def extract_and_save_memory(messages: list, task: str, path: str = _DEFAULT_MEMORY_FILE) -> str:
    """Use a lightweight LLM to extract a one-line summary, then persist it.

    Args:
        messages: Full conversation message list.
        task: The original user task string.
        path: Memory file path (injectable for tests).

    Returns:
        The extracted summary string.
    """
    from langchain_core.messages import HumanMessage
    import config

    history_lines = []
    for m in messages[-20:]:
        role = getattr(m, "type", "unknown")
        content = m.content if isinstance(m.content, str) else str(m.content)
        if content.strip():
            history_lines.append(f"[{role}]: {content[:500]}")
    history_str = "\n".join(history_lines)

    extract_prompt = (
        "You are a memory extraction assistant.\n"
        "Given this agent session, extract ONE concise summary sentence (max 80 words):\n"
        "- What task was completed\n"
        "- Key files created or modified\n"
        "- Any important outcomes or errors\n\n"
        f"Task: {task}\n\n"
        f"Session history:\n{history_str}\n\n"
        "Respond with ONLY the summary sentence."
    )

    memory_model = config.get_setting("MEMORY_MODEL", config.get_setting("MAIN_MODEL"))
    llm = config.get_llm(memory_model)
    response = llm.invoke([HumanMessage(content=extract_prompt)])
    summary = response.content.strip()

    memories = load_memories(path)
    memories.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "task": task[:100],
        "summary": summary,
    })
    save_memories(memories, path)

    return summary
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_memory.py -v
```

Expected: ALL PASS (note: `extract_and_save_memory` is tested in integration, not here)

- [ ] **Step 5: Commit**

```bash
git add memory.py tests/test_memory.py
git commit -m "feat: add cross-session long-term memory module"
```

---

### Task 5: Tools Module (Sandboxed Operations)

**Files:**
- Create: `harness-runtime/tools.py`
- Create: `harness-runtime/tests/test_tools.py`

- [ ] **Step 1: Write failing tests for tools**

`tests/test_tools.py`:

```python
"""Tests for tools module — sandboxed file operations."""

import os
import pytest
from tools import (
    list_files,
    read_file,
    write_file,
    delete_file,
    get_file_info,
    run_python,
    _safe_path,
    TOOLS,
)


class TestSafePath:
    def test_strips_directory_traversal(self, sandbox_dir):
        result = _safe_path("../../etc/passwd", sandbox_dir)
        assert result == os.path.join(sandbox_dir, "passwd")
        assert ".." not in result

    def test_normal_filename(self, sandbox_dir):
        result = _safe_path("main.py", sandbox_dir)
        assert result == os.path.join(sandbox_dir, "main.py")


class TestListFiles:
    def test_empty_sandbox(self, sandbox_dir):
        result = list_files.invoke({"sandbox_dir": sandbox_dir})
        assert "empty" in result.lower() or "Empty" in result

    def test_lists_created_files(self, sandbox_dir):
        open(os.path.join(sandbox_dir, "a.py"), "w").close()
        open(os.path.join(sandbox_dir, "b.txt"), "w").close()
        result = list_files.invoke({"sandbox_dir": sandbox_dir})
        assert "a.py" in result
        assert "b.txt" in result


class TestWriteAndReadFile:
    def test_write_then_read(self, sandbox_dir):
        write_result = write_file.invoke({
            "filename": "test.py",
            "content": "print('hello')",
            "sandbox_dir": sandbox_dir,
        })
        assert "written" in write_result.lower() or "Written" in write_result

        read_result = read_file.invoke({
            "filename": "test.py",
            "sandbox_dir": sandbox_dir,
        })
        assert "print('hello')" in read_result

    def test_read_nonexistent(self, sandbox_dir):
        result = read_file.invoke({"filename": "nope.py", "sandbox_dir": sandbox_dir})
        assert "not found" in result.lower()


class TestDeleteFile:
    def test_delete_existing(self, sandbox_dir):
        path = os.path.join(sandbox_dir, "tmp.py")
        open(path, "w").close()
        result = delete_file.invoke({"filename": "tmp.py", "sandbox_dir": sandbox_dir})
        assert "deleted" in result.lower() or "Deleted" in result
        assert not os.path.exists(path)

    def test_delete_nonexistent(self, sandbox_dir):
        result = delete_file.invoke({"filename": "nope.py", "sandbox_dir": sandbox_dir})
        assert "not found" in result.lower()


class TestToolsRegistry:
    def test_tools_list_has_six_tools(self):
        assert len(TOOLS) == 6

    def test_all_tools_have_names(self):
        names = {t.name for t in TOOLS}
        assert names == {"list_files", "read_file", "get_file_info", "write_file", "delete_file", "run_python"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: FAIL — `tools` module does not exist yet.

- [ ] **Step 3: Implement `tools.py`**

```python
"""
Tool Module
===========
Sandboxed tools available to the agent. All file ops confined to sandbox dir.

Safety levels (see guard.py):
  AUTO_APPROVE   : list_files, read_file, get_file_info
  ALWAYS_CONFIRM : write_file, delete_file
  KEYWORD_CHECK  : run_python
"""

import os
import subprocess
import tempfile

from langchain_core.tools import tool

# Default sandbox directory — cross-platform
_DEFAULT_SANDBOX = os.path.join(tempfile.gettempdir(), "harness_sandbox")
os.makedirs(_DEFAULT_SANDBOX, exist_ok=True)


def _safe_path(filename: str, sandbox: str = _DEFAULT_SANDBOX) -> str:
    """Prevent path traversal — force all paths inside sandbox."""
    return os.path.join(sandbox, os.path.basename(filename))


@tool
def list_files(sandbox_dir: str = _DEFAULT_SANDBOX) -> str:
    """List all files currently in the sandbox directory."""
    if not os.path.isdir(sandbox_dir):
        return "Sandbox directory does not exist."
    files = os.listdir(sandbox_dir)
    if not files:
        return "Sandbox is empty."
    return "Files in sandbox:\n" + "\n".join(f"  - {f}" for f in sorted(files))


@tool
def read_file(filename: str, sandbox_dir: str = _DEFAULT_SANDBOX) -> str:
    """Read and return the content of a file in the sandbox.

    Args:
        filename: Name of the file to read.
        sandbox_dir: Sandbox directory path.
    """
    path = _safe_path(filename, sandbox_dir)
    if not os.path.exists(path):
        return f"File not found: {filename}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if len(content) > 3000:
        content = content[:3000] + "\n... (truncated)"
    return content


@tool
def get_file_info(filename: str, sandbox_dir: str = _DEFAULT_SANDBOX) -> str:
    """Return metadata about a file in the sandbox (size, modified time).

    Args:
        filename: Name of the file to inspect.
        sandbox_dir: Sandbox directory path.
    """
    path = _safe_path(filename, sandbox_dir)
    if not os.path.exists(path):
        return f"File not found: {filename}"
    stat = os.stat(path)
    import datetime
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return f"{filename}\n  Size    : {stat.st_size} bytes\n  Modified: {mtime}"


@tool
def write_file(filename: str, content: str, sandbox_dir: str = _DEFAULT_SANDBOX) -> str:
    """Write content to a file inside the sandbox directory.

    Args:
        filename: Name of the file (e.g. 'main.py').
        content: Full content to write.
        sandbox_dir: Sandbox directory path.
    """
    path = _safe_path(filename, sandbox_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File written: {path} ({len(content)} chars)"


@tool
def delete_file(filename: str, sandbox_dir: str = _DEFAULT_SANDBOX) -> str:
    """Delete a file from the sandbox directory.

    Args:
        filename: Name of the file to delete.
        sandbox_dir: Sandbox directory path.
    """
    path = _safe_path(filename, sandbox_dir)
    if not os.path.exists(path):
        return f"File not found: {filename}"
    os.remove(path)
    return f"File deleted: {filename}"


@tool
def run_python(filename: str, sandbox_dir: str = _DEFAULT_SANDBOX) -> str:
    """Execute a Python file inside the sandbox directory.

    Args:
        filename: Name of the Python file to run.
        sandbox_dir: Sandbox directory path.
    """
    path = _safe_path(filename, sandbox_dir)
    if not os.path.exists(path):
        return f"Error: {filename} does not exist. Write the file first."
    try:
        result = subprocess.run(
            ["python", path],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=sandbox_dir,
        )
        output = result.stdout or result.stderr or "(no output)"
    except subprocess.TimeoutExpired:
        output = "Timeout: execution exceeded 15 seconds."
    if len(output) > 2000:
        output = output[:2000] + "\n... (output truncated)"
    return output


# ── Tool Registry ────────────────────────────────────────────────
TOOLS = [list_files, read_file, get_file_info, write_file, delete_file, run_python]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: add sandboxed tool module with 6 tools"
```

---

### Task 6: Prompts Module (Role-Specific System Prompts)

**Files:**
- Create: `harness-runtime/prompts.py`
- Create: `harness-runtime/tests/test_prompts.py`

- [ ] **Step 1: Write failing tests for prompts**

`tests/test_prompts.py`:

```python
"""Tests for prompts module — role-specific system prompts."""

import pytest
from prompts import get_prompt_for_phase, PHASES, get_system_prompt


class TestGetPromptForPhase:
    def test_architect_prompt_mentions_design(self):
        prompt = get_prompt_for_phase("architect")
        assert "architect" in prompt.lower() or "design" in prompt.lower()

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
        assert "design" in prompt.lower() or "architect" in prompt.lower()

    def test_includes_memory_when_present(self, monkeypatch):
        monkeypatch.setattr(
            "prompts.load_memories",
            lambda: [{"date": "2026-04-07", "summary": "built auth module"}],
        )
        prompt = get_system_prompt("implementer")
        assert "auth module" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_prompts.py -v
```

Expected: FAIL — `prompts` module does not exist yet.

- [ ] **Step 3: Implement `prompts.py`**

```python
"""
Prompt Management Module
========================
Role-specific system prompts for each agent phase.

Phases:
  architect    -> System design, module boundaries, API design
  implementer  -> Code implementation, bug fixes, refactoring
  tester       -> Test execution, evaluation, feedback
"""

from memory import format_memories_for_prompt, load_memories

PHASES = ("architect", "implementer", "tester")

_BASE_PROMPT = """You are an AI agent operating inside a safe harness.

Rules:
- You work inside the sandbox directory. All file operations are confined there.
- Explain what you are about to do before doing it.
- If a task is unclear, ask for clarification instead of guessing.
- Keep code clean, readable, and well-commented.
- Use immutable patterns where possible.

Workspace: sandbox directory (auto-assigned)
"""

_ARCHITECT_PROMPT = """## Your Role: Architect

You are the system architect. Your job is to analyze requirements and produce a design document.

Responsibilities:
- Define module boundaries and dependencies
- Design public interfaces (function signatures, data structures)
- Choose technology and library selections
- Document constraints and invariants
- Output a clear design specification that the implementer can follow

Design Principles:
- Interface isolation: each interface does one thing
- Dependency inversion: core logic depends on abstractions, not implementations
- Minimal exposure: keep the public API surface small
- Value semantics: prefer value types over reference types

Output Format:
Write a design document (design.md) to the sandbox that includes:
1. Module overview
2. Interface definitions (function signatures with types)
3. Data structures
4. Dependency graph
5. Constraints and invariants

When your design is complete, state "DESIGN COMPLETE" clearly.
"""

_IMPLEMENTER_PROMPT = """## Your Role: Implementer

You are the implementation engineer. Your job is to write code that fulfills the design specification.

Responsibilities:
- Implement interfaces defined by the architect
- Write clean, readable code following the design document
- Handle errors comprehensively
- Fix bugs reported by the tester

Coding Standards:
- No hardcoded values — use constants or config
- Functions < 50 lines, files < 500 lines
- Every error path handled explicitly
- Immutable patterns: create new objects instead of mutating

Workflow:
1. Read the design document in the sandbox
2. Implement each module as specified
3. Write the code files to the sandbox
4. When implementation is complete, state "IMPLEMENTATION COMPLETE"

If the tester has reported bugs, fix them and state "FIXES COMPLETE".
"""

_TESTER_PROMPT = """## Your Role: Tester

You are the test engineer. Your job is to verify the implementation against the design.

Responsibilities:
- Read the design document and implementation code
- Write test cases covering success paths and failure paths
- Execute the tests using run_python
- Report results clearly

Testing Approach:
1. Read the design spec (design.md) and all implementation files
2. Write a test file (test_impl.py) covering:
   - Happy path for each function/module
   - Edge cases and boundary conditions
   - Error handling paths
3. Run the test file
4. Evaluate results

Output Format:
After running tests, clearly state one of:
- "ALL TESTS PASSED" — if everything works as designed
- "TESTS FAILED" followed by a structured error list:
  - Which test failed
  - Expected vs actual behavior
  - Suggested fix

The implementer will use your error report to fix issues.
"""

_PHASE_PROMPTS = {
    "architect": _ARCHITECT_PROMPT,
    "implementer": _IMPLEMENTER_PROMPT,
    "tester": _TESTER_PROMPT,
}


def get_prompt_for_phase(phase: str) -> str:
    """Get the role-specific prompt for a given phase.

    Args:
        phase: One of "architect", "implementer", "tester".

    Returns:
        The role prompt string.

    Raises:
        KeyError: If phase is not recognized.
    """
    return _PHASE_PROMPTS[phase]


def get_system_prompt(phase: str) -> str:
    """Assemble the full system prompt: base rules + role prompt + memory.

    Args:
        phase: Current agent phase.

    Returns:
        Complete system prompt string.
    """
    base = _BASE_PROMPT.strip()
    role = get_prompt_for_phase(phase)
    memories = load_memories()
    memory_block = format_memories_for_prompt(memories)

    parts = [base, role.strip()]
    if memory_block:
        parts.append(memory_block)

    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_prompts.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add prompts.py tests/test_prompts.py
git commit -m "feat: add role-specific prompt module (architect/implementer/tester)"
```

---

### Task 7: Multi-Agent Orchestrator (LangGraph State Machine)

**Files:**
- Create: `harness-runtime/orchestrator.py`
- Create: `harness-runtime/tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests for orchestrator**

`tests/test_orchestrator.py`:

```python
"""Tests for orchestrator — multi-agent state machine transitions."""

import pytest
from orchestrator import (
    OrchestratorState,
    route_after_agent,
    route_after_guard,
    route_phase_transition,
    INITIAL_STATE,
)


class TestInitialState:
    def test_starts_with_architect_phase(self):
        assert INITIAL_STATE["phase"] == "architect"

    def test_starts_with_zero_steps(self):
        assert INITIAL_STATE["step_count"] == 0

    def test_starts_with_zero_retries(self):
        assert INITIAL_STATE["retry_count"] == 0

    def test_starts_approved(self):
        assert INITIAL_STATE["approved"] is True


class TestRouteAfterAgent:
    def _make_state(self, step_count=1, max_steps=15, has_tool_calls=False, content=""):
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.tool_calls = [{"name": "write_file", "args": {}}] if has_tool_calls else []
        msg.content = content
        return {
            "messages": [msg],
            "step_count": step_count,
            "max_steps": max_steps,
            "phase": "architect",
            "retry_count": 0,
            "approved": True,
        }

    def test_routes_to_guard_when_tool_calls(self):
        state = self._make_state(has_tool_calls=True)
        assert route_after_agent(state) == "guard"

    def test_routes_to_phase_transition_when_no_tool_calls(self):
        state = self._make_state(has_tool_calls=False)
        assert route_after_agent(state) == "phase_transition"

    def test_routes_to_end_when_max_steps_reached(self):
        state = self._make_state(step_count=15, max_steps=15)
        assert route_after_agent(state) == "__end__"


class TestRouteAfterGuard:
    def test_routes_to_tools_when_approved(self):
        state = {"approved": True}
        assert route_after_guard(state) == "tools"

    def test_routes_to_end_when_rejected(self):
        state = {"approved": False}
        assert route_after_guard(state) == "__end__"


class TestRoutePhaseTransition:
    def test_architect_goes_to_implementer(self):
        result = route_phase_transition({"phase": "architect", "retry_count": 0, "max_retries": 3})
        assert result["phase"] == "implementer"

    def test_implementer_goes_to_tester(self):
        result = route_phase_transition({"phase": "implementer", "retry_count": 0, "max_retries": 3})
        assert result["phase"] == "tester"

    def test_tester_pass_goes_to_done(self):
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.content = "ALL TESTS PASSED"
        state = {"phase": "tester", "retry_count": 0, "max_retries": 3, "messages": [msg]}
        result = route_phase_transition(state)
        assert result["phase"] == "done"

    def test_tester_fail_retries_implementer(self):
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.content = "TESTS FAILED: something broke"
        state = {"phase": "tester", "retry_count": 0, "max_retries": 3, "messages": [msg]}
        result = route_phase_transition(state)
        assert result["phase"] == "implementer"
        assert result["retry_count"] == 1

    def test_tester_fail_max_retries_goes_to_done(self):
        from unittest.mock import MagicMock
        msg = MagicMock()
        msg.content = "TESTS FAILED: still broken"
        state = {"phase": "tester", "retry_count": 3, "max_retries": 3, "messages": [msg]}
        result = route_phase_transition(state)
        assert result["phase"] == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_orchestrator.py -v
```

Expected: FAIL — `orchestrator` module does not exist yet.

- [ ] **Step 3: Implement `orchestrator.py`**

```python
"""
Multi-Agent Orchestrator
========================
LangGraph state machine that implements the architect -> implementer -> tester
self-healing loop.

Graph topology:
  agent_node -> route_after_agent
    ├── has tool calls? -> guard_node -> route_after_guard
    │                        ├── approved -> tool_node -> agent_node (loop)
    │                        └── rejected -> END
    ├── max steps? -> END
    └── no tool calls -> phase_transition -> route_after_phase
                            ├── phase != done -> agent_node (next role)
                            └── phase == done -> END
"""

from typing import Annotated

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

import config
from guard import should_confirm, request_human_approval
from prompts import get_system_prompt
from tools import TOOLS


# ── State Definition ───────────────────────────────────────────────

class OrchestratorState(TypedDict):
    messages: Annotated[list, add_messages]
    phase: str          # "architect" | "implementer" | "tester" | "done"
    step_count: int
    max_steps: int
    max_retries: int
    retry_count: int
    approved: bool


INITIAL_STATE: OrchestratorState = {
    "messages": [],
    "phase": "architect",
    "step_count": 0,
    "max_steps": int(config.get_setting("MAX_STEPS", "15")),
    "max_retries": int(config.get_setting("MAX_RETRIES", "3")),
    "retry_count": 0,
    "approved": True,
}


# ── Nodes ──────────────────────────────────────────────────────────

def agent_node(state: OrchestratorState) -> dict:
    """Model inference node. Uses phase to select the correct role prompt."""
    phase = state["phase"]
    system_prompt = get_system_prompt(phase)
    system_msg = SystemMessage(content=system_prompt)
    messages = [system_msg] + state["messages"]

    step = state["step_count"] + 1
    max_s = state["max_steps"]
    print(f"\n[HARNESS] Step {step}/{max_s} | Phase: {phase} | Thinking...")

    llm = config.get_llm().bind_tools(TOOLS)
    response = llm.invoke(messages)

    return {
        "messages": [response],
        "step_count": step,
    }


def guard_node(state: OrchestratorState) -> dict:
    """Safety guard node. Checks tool calls for dangerous operations."""
    last = state["messages"][-1]
    approved = True

    if hasattr(last, "tool_calls") and last.tool_calls:
        for call in last.tool_calls:
            if should_confirm(call["name"], call["args"]):
                approved = request_human_approval(call["name"], call["args"])
                if not approved:
                    break

    return {"approved": approved}


tool_node = ToolNode(TOOLS)


def phase_transition_node(state: OrchestratorState) -> dict:
    """Transition between agent phases based on current phase and results."""
    result = route_phase_transition(state)
    phase = result["phase"]

    if phase == "done":
        print(f"\n[HARNESS] All phases complete. Retry count: {state['retry_count']}")
    else:
        prev = state["phase"]
        if phase == "implementer" and prev == "tester":
            print(f"\n[HARNESS] Tests failed. Retrying implementation (attempt {result['retry_count']}/{state['max_retries']})")
        else:
            print(f"\n[HARNESS] Phase transition: {prev} -> {phase}")

    return result


# ── Routing Functions ──────────────────────────────────────────────

def route_after_agent(state: OrchestratorState) -> str:
    """After agent thinks: check for tool calls, max steps, or phase transition."""
    if state["step_count"] >= state["max_steps"]:
        print(f"\n[HARNESS] Max steps ({state['max_steps']}) reached. Stopping.")
        return END

    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "guard"

    return "phase_transition"


def route_after_guard(state: OrchestratorState) -> str:
    """After guard: proceed to tools if approved, else stop."""
    return "tools" if state["approved"] else END


def route_after_phase(state: OrchestratorState) -> str:
    """After phase transition: continue to next agent or end."""
    return END if state["phase"] == "done" else "agent"


def route_phase_transition(state: OrchestratorState) -> dict:
    """Determine the next phase based on current phase and test results.

    Returns:
        Dict with updated phase (and optionally retry_count).
    """
    phase = state["phase"]

    if phase == "architect":
        return {"phase": "implementer"}

    if phase == "implementer":
        return {"phase": "tester"}

    if phase == "tester":
        last = state["messages"][-1]
        content = last.content if isinstance(last.content, str) else str(last.content)

        if "ALL TESTS PASSED" in content.upper():
            return {"phase": "done"}

        if state["retry_count"] < state["max_retries"]:
            return {"phase": "implementer", "retry_count": state["retry_count"] + 1}

        print(f"\n[HARNESS] Max retries ({state['max_retries']}) reached. Finishing with failures.")
        return {"phase": "done"}

    return {"phase": "done"}


# ── Graph Builder ──────────────────────────────────────────────────

def build_orchestrator() -> StateGraph:
    """Build and compile the multi-agent LangGraph."""
    graph = StateGraph(OrchestratorState)

    graph.add_node("agent", agent_node)
    graph.add_node("guard", guard_node)
    graph.add_node("tools", tool_node)
    graph.add_node("phase_transition", phase_transition_node)

    graph.set_entry_point("agent")

    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_conditional_edges("guard", route_after_guard)
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("phase_transition", route_after_phase)

    return graph.compile()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_orchestrator.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add multi-agent orchestrator with architect/implementer/tester loop"
```

---

### Task 8: CLI Entry Point

**Files:**
- Create: `harness-runtime/main.py`

- [ ] **Step 1: Implement `main.py`**

```python
"""
MicroHarness — Multi-Agent CLI Entry Point
===========================================
Reads task from user, runs the architect -> implementer -> tester loop,
saves session memory.

Usage:
  python main.py                  # Multi-agent mode (default)
  python main.py --single         # Single-agent mode (no phase routing)
  python main.py --phase tester   # Start from a specific phase
"""

import argparse
import sys

from langchain_core.messages import HumanMessage

import config
from memory import extract_and_save_memory, load_memories
from orchestrator import OrchestratorState, INITIAL_STATE, build_orchestrator


def print_banner():
    provider = config.get_setting("PROVIDER", "anthropic")
    main_model = config.get_setting("MAIN_MODEL", "claude-sonnet-4-20250514")
    memory_model = config.get_setting("MEMORY_MODEL", main_model)
    max_steps = config.get_setting("MAX_STEPS", "15")
    max_retries = config.get_setting("MAX_RETRIES", "3")

    print("=" * 55)
    print("  Harness Runtime — Multi-Agent Orchestrator")
    print(f"  Provider     : {provider}")
    print(f"  Main Model   : {main_model}")
    print(f"  Memory Model : {memory_model}")
    print(f"  Max Steps    : {max_steps}")
    print(f"  Max Retries  : {max_retries}")
    print("=" * 55)


def main():
    parser = argparse.ArgumentParser(description="Harness Runtime — Multi-Agent Dev Loop")
    parser.add_argument("--single", action="store_true", help="Single-agent mode (no phase routing)")
    parser.add_argument("--phase", default="architect", choices=["architect", "implementer", "tester"],
                        help="Starting phase (default: architect)")
    args = parser.parse_args()

    config.validate()
    print_banner()

    existing = load_memories()
    if existing:
        print(f"\n[HARNESS] Found {len(existing)} memory record(s).")
        print(f"          Last: {existing[-1]['date']} — {existing[-1]['summary'][:60]}...")
    else:
        print("\n[HARNESS] No long-term memory found. Starting fresh.")

    print("\nDescribe your task:")
    print("  Multi-agent mode: architect -> implementer -> tester (auto-loop)")
    if args.single:
        print("  [SINGLE-AGENT MODE] — no phase routing")
    print()

    user_input = input("Task: ").strip()
    if not user_input:
        print("No task provided. Exiting.")
        return

    init_state: OrchestratorState = {
        **INITIAL_STATE,
        "messages": [HumanMessage(content=user_input)],
        "phase": args.phase if not args.single else "implementer",
    }

    if args.single:
        init_state["max_retries"] = 0

    print("\n[HARNESS] Starting orchestrator...\n")
    orchestrator = build_orchestrator()
    final_state = orchestrator.invoke(init_state)

    final_messages = final_state["messages"]
    final_response = next(
        (m for m in reversed(final_messages)
         if hasattr(m, "content") and isinstance(m.content, str) and m.content.strip()),
        None,
    )

    print("\n" + "=" * 55)
    print("  FINAL RESPONSE")
    print("=" * 55)
    print(final_response.content if final_response else "(Task completed — see tool outputs above)")
    print("=" * 55)
    print(f"  Phase     : {final_state['phase']}")
    print(f"  Steps used: {final_state['step_count']}/{final_state['max_steps']}")
    print(f"  Retries   : {final_state['retry_count']}/{final_state['max_retries']}")
    print("=" * 55)

    print("\n[HARNESS] Extracting long-term memory...")
    summary = extract_and_save_memory(final_state["messages"], user_input)
    print(f"[HARNESS] Memory saved: {summary}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax is valid**

```bash
cd harness-runtime
python -c "import py_compile; py_compile.compile('main.py', doraise=True)"
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add CLI entry point with single/multi-agent modes"
```

---

### Task 9: Integration Test and Documentation

**Files:**
- Modify: `harness-runtime/tests/test_orchestrator.py` (add integration test)
- Modify: `README.md` (add harness-runtime section)

- [ ] **Step 1: Add integration test for full graph build**

Append to `tests/test_orchestrator.py`:

```python
class TestGraphBuild:
    def test_build_orchestrator_returns_compiled_graph(self):
        """Verify the LangGraph compiles without errors."""
        from orchestrator import build_orchestrator
        graph = build_orchestrator()
        assert graph is not None

    def test_orchestrator_has_expected_nodes(self):
        """Compiled graph should contain all 4 nodes."""
        from orchestrator import build_orchestrator
        graph = build_orchestrator()
        node_names = set(graph.get_graph().nodes.keys())
        assert "agent" in node_names
        assert "guard" in node_names
        assert "tools" in node_names
        assert "phase_transition" in node_names
```

- [ ] **Step 2: Run full test suite**

```bash
cd harness-runtime
python -m pytest tests/ -v --tb=short
```

Expected: ALL PASS

- [ ] **Step 3: Run coverage report**

```bash
python -m pytest tests/ --cov=. --cov-report=term-missing --ignore=tests/
```

Expected: 80%+ coverage on config, guard, memory, prompts, orchestrator routing logic.

- [ ] **Step 4: Update project README.md**

Add a new section to `README.md` under the existing structure:

```markdown
## harness-runtime (NEW)

基于 [microharness](https://github.com/jingw2/microharness) 整合的可运行 Agent 引擎，实现多 Provider 支持 + 多 Agent 自动闭环。

### 特性

- **10+ Provider 支持**：Anthropic、OpenAI、DeepSeek、Kimi、Qwen、GLM、MiniMax、Xiaomi、Ollama、Custom
- **多 Agent 闭环**：architect → implementer → tester 自动循环，失败自动修复（最多 N 轮）
- **3 级安全守卫**：auto-approve / always-confirm / keyword-check
- **跨会话记忆**：自动提炼会话要点，下次启动时注入上下文
- **沙箱隔离**：所有文件操作限定在临时目录内

### 快速开始

​```bash
cd harness-runtime
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your provider and API key
python main.py
​```

### 架构

| 层 | 文件 | 职责 |
|---|---|---|
| Config | config.py | 读 .env，按 provider 构建 LLM 实例 |
| Prompts | prompts.py | 三角色系统提示 + 长期记忆注入 |
| Tools | tools.py | 6 个沙箱工具，路径穿越防护 |
| Guard | guard.py | 3 级分类，人工确认 |
| Orchestrator | orchestrator.py | LangGraph 多 Agent 状态机 |
| Memory | memory.py | 跨会话持久化，memory.json |
| CLI | main.py | 入口，支持 --single / --phase 参数 |
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_orchestrator.py README.md
git commit -m "docs: add harness-runtime integration tests and documentation"
```

---

## Execution Summary

| Task | Description | Files | Est. |
|------|------------|-------|------|
| 1 | Scaffolding | requirements.txt, .env.example, conftest.py | 5 min |
| 2 | Config module | config.py + test | 10 min |
| 3 | Guard module | guard.py + test | 8 min |
| 4 | Memory module | memory.py + test | 8 min |
| 5 | Tools module | tools.py + test | 10 min |
| 6 | Prompts module | prompts.py + test | 8 min |
| 7 | Orchestrator | orchestrator.py + test | 15 min |
| 8 | CLI entry | main.py | 5 min |
| 9 | Integration + docs | tests + README | 8 min |
