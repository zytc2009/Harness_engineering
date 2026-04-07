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
        assert "empty" in result.lower()

    def test_lists_created_files(self, sandbox_dir):
        open(os.path.join(sandbox_dir, "a.py"), "w").close()
        open(os.path.join(sandbox_dir, "b.txt"), "w").close()
        result = list_files.invoke({"sandbox_dir": sandbox_dir})
        assert "a.py" in result
        assert "b.txt" in result


class TestWriteAndReadFile:
    def test_write_then_read(self, sandbox_dir):
        write_file.invoke({
            "filename": "test.py",
            "content": "print('hello')",
            "sandbox_dir": sandbox_dir,
        })
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
        assert "deleted" in result.lower()
        assert not os.path.exists(path)

    def test_delete_nonexistent(self, sandbox_dir):
        result = delete_file.invoke({"filename": "nope.py", "sandbox_dir": sandbox_dir})
        assert "not found" in result.lower()


class TestRunPython:
    def test_run_existing_script(self, sandbox_dir):
        script_path = os.path.join(sandbox_dir, "hello.py")
        with open(script_path, "w") as f:
            f.write("print('hello world')")
        result = run_python.invoke({"filename": "hello.py", "sandbox_dir": sandbox_dir})
        assert "hello world" in result

    def test_run_nonexistent(self, sandbox_dir):
        result = run_python.invoke({"filename": "nope.py", "sandbox_dir": sandbox_dir})
        assert "does not exist" in result.lower()


class TestToolsRegistry:
    def test_tools_list_has_six_tools(self):
        assert len(TOOLS) == 6

    def test_all_tools_have_names(self):
        names = {t.name for t in TOOLS}
        assert names == {"list_files", "read_file", "get_file_info", "write_file", "delete_file", "run_python"}
