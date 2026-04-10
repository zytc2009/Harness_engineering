"""Tests for queue/drain behavior in main.py."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from status import read_status
from task_queue import add_task, load_queue


class TestHandleAdd:
    def test_handle_add_writes_pending_task(self, tmp_path):
        queue_path = tmp_path / "q.json"
        with patch("main._QUEUE_FILE", queue_path):
            from main import handle_add

            task_id = handle_add("build calculator", max_retries=2)

        queue = load_queue(queue_path)
        assert queue[0]["id"] == task_id
        assert queue[0]["status"] == "pending"
        assert queue[0]["max_retries"] == 2


class TestRunDrain:
    def test_run_drain_processes_two_successful_tasks(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        add_task("task A", queue_path)
        add_task("task B", queue_path)

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.SANDBOX", sandbox_root),
            patch("main.config.validate"),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
            patch("main.run_pipeline", return_value={"phase": "done", "retry_count": 0, "tester_report": ""}),
        ):
            from main import run_drain

            run_drain(max_retries=2)

        queue = load_queue(queue_path)
        assert [task["status"] for task in queue] == ["done", "done"]
        status = read_status(status_path)
        assert status["worker_state"] == "idle"

    def test_run_drain_continues_after_failure(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        add_task("will fail", queue_path)
        add_task("will pass", queue_path)
        results = iter([
            {"phase": "done", "retry_count": 2, "tester_report": "err", "failed": True},
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
        assert queue[0]["status"] == "failed"
        assert queue[1]["status"] == "done"

    def test_run_drain_repairs_stale_running_tasks_before_processing(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        stale_id = add_task("stale", queue_path)
        add_task("fresh", queue_path)

        from task_queue import update_task

        update_task(stale_id, queue_path=queue_path, status="running")

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.SANDBOX", sandbox_root),
            patch("main.config.validate"),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
            patch("main.run_pipeline", return_value={"phase": "done", "retry_count": 0, "tester_report": ""}),
        ):
            from main import run_drain

            run_drain(max_retries=2)

        queue = load_queue(queue_path)
        assert queue[0]["status"] == "failed"
        assert queue[0]["error"] == "worker_interrupted"
        assert queue[1]["status"] == "done"

    def test_keyboard_interrupt_stops_drain_and_leaves_remaining_pending(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        add_task("interrupt me", queue_path)
        add_task("pending later", queue_path)

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.SANDBOX", sandbox_root),
            patch("main.config.validate"),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
            patch("main.run_pipeline", side_effect=KeyboardInterrupt),
        ):
            from main import run_drain

            run_drain(max_retries=2)

        queue = load_queue(queue_path)
        assert queue[0]["status"] == "failed"
        assert queue[0]["error"] == "interrupted"
        assert queue[1]["status"] == "pending"
        status = read_status(status_path)
        assert status["worker_state"] == "stopped"
