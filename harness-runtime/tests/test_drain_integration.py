"""Integration tests for drain queue processing."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from status import read_status
from task_queue import add_task, load_queue


class TestDrainIntegration:
    def test_full_queue_drain(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        add_task("task A", queue_path)
        add_task("task B", queue_path)
        add_task("task C", queue_path)

        call_count = 0

        def mock_pipeline(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("on_status"):
                kwargs["on_status"]({
                    "type": "phase_started",
                    "phase": "implementer",
                    "retry_count": 0,
                    "error": None,
                })
                kwargs["on_status"]({
                    "type": "pipeline_done",
                    "phase": None,
                    "retry_count": 0,
                    "error": None,
                })
            return {"phase": "done", "retry_count": 0, "tester_report": ""}

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.SANDBOX", sandbox_root),
            patch("main.config.validate"),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
            patch("main.run_pipeline", side_effect=mock_pipeline),
        ):
            from main import run_drain

            run_drain(max_retries=3)

        assert call_count == 3
        queue = load_queue(queue_path)
        assert all(task["status"] == "done" for task in queue)
        status = read_status(status_path)
        assert status["worker_state"] == "idle"

    def test_mixed_success_and_failure_keep_fifo(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        add_task("will fail", queue_path)
        add_task("will pass", queue_path)

        results = iter([
            {"phase": "done", "retry_count": 2, "tester_report": "bad", "failed": True},
            {"phase": "done", "retry_count": 0, "tester_report": ""},
        ])

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.SANDBOX", sandbox_root),
            patch("main.config.validate"),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
            patch("main.run_pipeline", side_effect=lambda **kwargs: next(results)),
        ):
            from main import run_drain

            run_drain(max_retries=2)

        queue = load_queue(queue_path)
        assert [task["status"] for task in queue] == ["failed", "done"]

    def test_each_task_uses_its_own_sandbox_dir(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        first_id = add_task("first", queue_path)
        second_id = add_task("second", queue_path)
        seen = []

        def mock_pipeline(**kwargs):
            seen.append(Path(kwargs["sandbox_dir"]))
            return {"phase": "done", "retry_count": 0, "tester_report": ""}

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.SANDBOX", sandbox_root),
            patch("main.config.validate"),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
            patch("main.run_pipeline", side_effect=mock_pipeline),
        ):
            from main import run_drain

            run_drain(max_retries=2)

        assert seen == [sandbox_root / first_id, sandbox_root / second_id]
