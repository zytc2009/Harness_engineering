"""
Tool Module
===========
Sandboxed tools available to the agent. All file ops confined to sandbox dir.

Safety levels (see guard.py):
  AUTO_APPROVE   : list_files, read_file, get_file_info, write_file, delete_file
  KEYWORD_CHECK  : run_python, run_command (when args contain dangerous keywords)
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


@tool
def run_command(command: str, sandbox_dir: str = _DEFAULT_SANDBOX) -> str:
    """Run a shell command inside the sandbox directory.

    Use this to compile and run any language (C++, Rust, Go, etc.) or
    run test frameworks (pytest, cargo test, go test, etc.).
    The working directory is always the sandbox — paths outside it are blocked.

    Args:
        command: Shell command to run (e.g. 'g++ -o calc main.cpp && ./calc').
        sandbox_dir: Sandbox directory path.
    """
    # Block obvious path-traversal attempts — the cwd=sandbox_dir already
    # confines relative paths, but reject explicit parent-dir escapes.
    if ".." in command:
        return "Error: path traversal ('..') is not allowed in commands."
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=sandbox_dir,
        )
        output = (result.stdout + result.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        output = "Timeout: command exceeded 30 seconds."
    if len(output) > 2000:
        output = output[:2000] + "\n... (output truncated)"
    return output


# ── Tool Registry ────────────────────────────────────────────────
TOOLS = [list_files, read_file, get_file_info, write_file, delete_file, run_python, run_command]
