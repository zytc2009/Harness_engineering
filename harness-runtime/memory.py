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

_DEFAULT_MEMORY_FILE = str(Path(__file__).parent / "task" / "memory.json")


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
    Path(path).parent.mkdir(parents=True, exist_ok=True)
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
