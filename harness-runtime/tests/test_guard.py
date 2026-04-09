"""Tests for guard module — 3-tier safety classification."""

import pytest
from guard import (
    AUTO_APPROVE_TOOLS,
    ALWAYS_CONFIRM_TOOLS,
    is_dangerous,
    classify_tool,
    should_confirm,
)


class TestClassifyTool:
    def test_read_tools_are_auto_approve(self):
        assert classify_tool("list_files", {}) == "auto_approve"
        assert classify_tool("read_file", {"filename": "x.py"}) == "auto_approve"
        assert classify_tool("get_file_info", {"filename": "x.py"}) == "auto_approve"

    def test_sandbox_tools_are_auto_approve(self):
        assert classify_tool("write_file", {"filename": "x.py", "content": "hi"}) == "auto_approve"
        assert classify_tool("delete_file", {"filename": "x.py"}) == "auto_approve"

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


class TestShouldConfirm:
    def test_read_tools_no_confirm(self):
        assert should_confirm("list_files", {}) is False
        assert should_confirm("read_file", {"filename": "x"}) is False

    def test_sandbox_tools_no_confirm(self):
        assert should_confirm("write_file", {"filename": "x", "content": "y"}) is False
        assert should_confirm("delete_file", {"filename": "x"}) is False

    def test_dangerous_content_confirms(self):
        assert should_confirm("run_python", {"content": "os.system('rm -rf /')"}) is True


class TestToolSets:
    def test_no_overlap(self):
        assert AUTO_APPROVE_TOOLS.isdisjoint(ALWAYS_CONFIRM_TOOLS)
