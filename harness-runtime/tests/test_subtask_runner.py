"""Tests for subtask_runner module."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from subtask_runner import SubtaskResult, _resolve_workspace, run_subtasks

SUBTASK = {
    "id": 1,
    "title": "Implement parser",
    "description": "Parse stdin JSON",
    "files": ["parser.py"],
    "acceptance_criteria": "Returns dict on valid input",
}


class TestResolveWorkspace:
    def test_uses_workspace_dir_when_provided(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        with patch("subtask_runner.git_ops.ensure_git_repo") as mock_ensure:
            result = _resolve_workspace(ws, tmp_path / "sandbox")
        assert result == ws
        mock_ensure.assert_called_once_with(ws)

    def test_falls_back_to_sandbox_when_no_workspace(self, tmp_path):
        with patch("subtask_runner.git_ops.ensure_git_repo") as mock_ensure:
            result = _resolve_workspace(None, tmp_path)
        assert result == tmp_path
        mock_ensure.assert_called_once_with(tmp_path)

    def test_creates_workspace_dir_if_missing(self, tmp_path):
        ws = tmp_path / "does_not_exist"
        with patch("subtask_runner.git_ops.ensure_git_repo"):
            result = _resolve_workspace(ws, tmp_path)
        assert ws.exists()


class TestRunSubtasks:
    def _make_metadata(self, **constraints):
        return {"constraints": constraints}

    def test_single_passing_subtask_returns_passed(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="# sub design"),
            patch("subtask_runner.implementer_phase", return_value={"parser.py": "x=1"}),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="abc123"),
        ):
            results = run_subtasks(
                task="build parser",
                design="# design",
                subtasks=[SUBTASK],
                sandbox_dir=tmp_path,
                workspace_dir=None,
                max_retries=3,
                on_status=None,
                task_metadata=None,
            )
        assert len(results) == 1
        assert results[0].status == "passed"
        assert results[0].commit_sha == "abc123"

    def test_implementer_no_files_retries_then_skips(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="# sub design"),
            patch("subtask_runner.implementer_phase", return_value={}),
            patch("subtask_runner.git_ops.ensure_git_repo"),
        ):
            results = run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=2, on_status=None, task_metadata=None,
            )
        assert results[0].status == "skipped"
        assert results[0].retry_count == 2

    def test_failed_subtask_does_not_stop_next(self, tmp_path):
        subtasks = [
            {**SUBTASK, "id": 1, "title": "first"},
            {**SUBTASK, "id": 2, "title": "second", "files": ["b.py"]},
        ]
        call_count = {"n": 0}

        def fake_implementer(task, design, feedback="", sandbox_dir=None, task_metadata=None):
            call_count["n"] += 1
            return {} if call_count["n"] == 1 else {"b.py": "y=2"}

        with (
            patch("subtask_runner.architect_phase", return_value="# sub design"),
            patch("subtask_runner.implementer_phase", side_effect=fake_implementer),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            results = run_subtasks(
                task="t", design="d", subtasks=subtasks,
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=1, on_status=None, task_metadata=None,
            )
        assert results[0].status == "skipped"
        assert results[1].status == "passed"

    def test_tester_runs_when_subtask_tester_true(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.tester_phase", return_value=(True, "ok")) as mock_tester,
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=None,
                task_metadata=self._make_metadata(subtask_tester="true"),
            )
        mock_tester.assert_called_once()

    def test_tester_skipped_when_subtask_tester_false(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.tester_phase") as mock_tester,
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=None, task_metadata=None,
            )
        mock_tester.assert_not_called()

    def test_subtask_tester_last_only_runs_only_on_last(self, tmp_path):
        subtasks = [
            {**SUBTASK, "id": 1, "title": "first"},
            {**SUBTASK, "id": 2, "title": "second", "files": ["b.py"]},
        ]
        tester_calls = []

        def fake_tester(task, design, code_files, sandbox_dir=None, task_metadata=None):
            tester_calls.append(code_files)
            return (True, "ok")

        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.tester_phase", side_effect=fake_tester),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            run_subtasks(
                task="t", design="d", subtasks=subtasks,
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=None,
                task_metadata=self._make_metadata(subtask_tester_last_only="true"),
            )
        assert len(tester_calls) == 1  # only last subtask

    def test_git_commit_failure_does_not_skip_subtask(self, tmp_path):
        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", side_effect=RuntimeError("git error")),
        ):
            results = run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=None, task_metadata=None,
            )
        assert results[0].status == "passed"  # not skipped despite git failure
        assert results[0].commit_sha == ""

    def test_on_status_callback_called(self, tmp_path):
        events = []
        with (
            patch("subtask_runner.architect_phase", return_value="d"),
            patch("subtask_runner.implementer_phase", return_value={"f.py": "x"}),
            patch("subtask_runner.git_ops.ensure_git_repo"),
            patch("subtask_runner.git_ops.commit_subtask", return_value="sha"),
        ):
            run_subtasks(
                task="t", design="d", subtasks=[SUBTASK],
                sandbox_dir=tmp_path, workspace_dir=None,
                max_retries=3, on_status=events.append, task_metadata=None,
            )
        types = [e["type"] for e in events]
        assert "subtask_started" in types
        assert "subtask_finished" in types
