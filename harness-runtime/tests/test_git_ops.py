"""Tests for git_ops module."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import git_ops


class TestEnsureGitRepo:
    def test_initializes_fresh_directory(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        assert (tmp_path / ".git").exists()

    def test_idempotent_on_existing_repo(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        git_ops.ensure_git_repo(tmp_path)  # must not raise
        assert (tmp_path / ".git").exists()

    def test_sets_local_git_identity(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        result = subprocess.run(
            ["git", "config", "user.email"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert result.stdout.strip() == "harness@local"

    def test_does_not_override_identity_on_existing_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "custom@example.com"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
        git_ops.ensure_git_repo(tmp_path)  # repo already exists — must not overwrite config
        result = subprocess.run(
            ["git", "config", "user.email"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert result.stdout.strip() == "custom@example.com"


class TestCommitSubtask:
    def test_returns_40_char_sha(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        (tmp_path / "hello.py").write_text("x = 1", encoding="utf-8")
        sha = git_ops.commit_subtask(tmp_path, ["hello.py"], "[subtask 1/2] add hello")
        assert len(sha) == 40
        assert sha.isalnum()

    def test_commit_message_appears_in_log(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        (tmp_path / "a.py").write_text("pass", encoding="utf-8")
        git_ops.commit_subtask(tmp_path, ["a.py"], "[subtask 1/1] test message")
        log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert "[subtask 1/1] test message" in log.stdout

    def test_only_specified_files_are_staged(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        (tmp_path / "included.py").write_text("x = 1", encoding="utf-8")
        (tmp_path / "excluded.py").write_text("y = 2", encoding="utf-8")
        git_ops.commit_subtask(tmp_path, ["included.py"], "partial commit")
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert "excluded.py" in status.stdout  # still untracked


class TestGetHeadSha:
    def test_returns_sha_after_commit(self, tmp_path):
        git_ops.ensure_git_repo(tmp_path)
        (tmp_path / "f.py").write_text("1", encoding="utf-8")
        committed_sha = git_ops.commit_subtask(tmp_path, ["f.py"], "c")
        assert git_ops.get_head_sha(tmp_path) == committed_sha

    def test_returns_empty_string_when_no_commits(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        assert git_ops.get_head_sha(tmp_path) == ""
