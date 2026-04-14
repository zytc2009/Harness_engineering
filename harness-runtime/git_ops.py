"""Git operations for subtask commit tracking."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_HARNESS_EMAIL = "harness@local"
_HARNESS_NAME = "harness"


def _git(directory: Path, *args: str, text: bool = False) -> subprocess.CompletedProcess:
    """Run a git command in directory, raising on non-zero exit."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(directory),
            check=True,
            capture_output=True,
            text=text,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("git %s failed in %s: %s", list(args), directory, exc.stderr)
        raise


def ensure_git_repo(directory: Path) -> None:
    """Initialize a git repo with local identity if not already one.

    If the directory is already a git repo, does nothing (including not
    overwriting any existing identity config).
    """
    if (directory / ".git").exists():
        return
    _git(directory, "init")
    _git(directory, "config", "user.email", _HARNESS_EMAIL)
    _git(directory, "config", "user.name", _HARNESS_NAME)


def commit_subtask(directory: Path, files: list[str], message: str) -> str:
    """Stage files and create a commit. Returns the new HEAD SHA (40 chars)."""
    _git(directory, "add", "--", *files)
    _git(directory, "commit", "-m", message)
    return get_head_sha(directory)


def get_head_sha(directory: Path) -> str:
    """Return the current HEAD SHA, or empty string if no commits exist."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(directory),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""
