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
