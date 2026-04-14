"""Git operations for subtask commit tracking."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_git_repo(directory: Path) -> None:
    """Initialize a git repo with local identity if not already one.

    If the directory is already a git repo, does nothing (including not
    overwriting any existing identity config).
    """
    git_dir = directory / ".git"
    if git_dir.exists():
        return
    subprocess.run(["git", "init"], cwd=str(directory), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "harness@local"],
        cwd=str(directory), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "harness"],
        cwd=str(directory), check=True, capture_output=True,
    )


def commit_subtask(directory: Path, files: list[str], message: str) -> str:
    """Stage files and create a commit. Returns the new HEAD SHA (40 chars)."""
    subprocess.run(
        ["git", "add", "--"] + files,
        cwd=str(directory), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(directory), check=True, capture_output=True,
    )
    return get_head_sha(directory)


def get_head_sha(directory: Path) -> str:
    """Return the current HEAD SHA, or empty string if no commits exist."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(directory), capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""
