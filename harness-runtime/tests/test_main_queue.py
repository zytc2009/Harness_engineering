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
        status_path = tmp_path / "status.json"
        with patch("main._QUEUE_FILE", queue_path), patch("main._STATUS_FILE", status_path):
            from main import handle_add

            task_id = handle_add("build calculator", max_retries=2)

        queue = load_queue(queue_path)
        assert queue[0]["id"] == task_id
        assert queue[0]["status"] == "pending"
        assert queue[0]["max_retries"] == 2
        status = read_status(status_path)
        assert status["worker_state"] == "idle"
        assert status["queue_pending"] == 1
        assert status["last_event_type"] == "task_queued"


class TestQueueControls:
    def test_handle_cancel_marks_task_cancelled(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        task_id = add_task("cancel me", queue_path)

        from status import update_status
        update_status(
            worker_state="idle",
            current_task_id=None,
            current_task_description=None,
            last_task_id="done-1",
            last_task_description="completed before",
            phase=None,
            task_state=None,
            last_task_finished_at="2026-04-10 10:00:00",
            status_path=status_path,
        )

        with patch("main._QUEUE_FILE", queue_path), patch("main._STATUS_FILE", status_path):
            from main import handle_cancel

            handle_cancel(task_id)

        queue = load_queue(queue_path)
        assert queue[0]["status"] == "cancelled"
        status = read_status(status_path)
        assert status["last_task_id"] == "done-1"
        assert status["last_task_finished_at"] == "2026-04-10 10:00:00"

    def test_handle_skip_marks_task_skipped(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        task_id = add_task("skip me", queue_path)

        from status import update_status
        update_status(
            worker_state="idle",
            current_task_id=None,
            current_task_description=None,
            last_task_id="done-2",
            last_task_description="completed before",
            phase=None,
            task_state=None,
            last_task_finished_at="2026-04-10 10:00:00",
            status_path=status_path,
        )

        with patch("main._QUEUE_FILE", queue_path), patch("main._STATUS_FILE", status_path):
            from main import handle_skip

            handle_skip(task_id)

        queue = load_queue(queue_path)
        assert queue[0]["status"] == "skipped"
        status = read_status(status_path)
        assert status["last_task_id"] == "done-2"
        assert status["last_task_finished_at"] == "2026-04-10 10:00:00"


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
        assert status["queue_cancelled"] == 0
        assert status["queue_skipped"] == 0
        assert status["last_event_type"] == "worker_idle"
        assert status["last_task_id"] == queue[1]["id"]
        assert status["last_task_description"] == "task B"

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

    def test_run_drain_records_unexpected_exception_in_status(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        task_id = add_task("boom", queue_path)

        with (
            patch("main._QUEUE_FILE", queue_path),
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.SANDBOX", sandbox_root),
            patch("main.config.validate"),
            patch("main.print_banner"),
            patch("main.run_pipeline", side_effect=RuntimeError("boom")),
        ):
            from main import run_drain

            run_drain(max_retries=2)

        queue = load_queue(queue_path)
        assert queue[0]["status"] == "failed"
        status = read_status(status_path)
        assert status["worker_state"] == "idle"
        assert status["queue_failed"] == 1
        assert status["last_task_id"] == task_id
        assert status["last_task_description"] == "boom"

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
        assert status["last_event_type"] == "pipeline_interrupted"

    def test_drain_ignores_cancelled_and_skipped_tasks(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        first = add_task("cancelled", queue_path)
        second = add_task("skipped", queue_path)
        third = add_task("run me", queue_path)

        from task_queue import cancel_task, skip_task

        cancel_task(first, queue_path)
        skip_task(second, queue_path)

        seen = []

        def mock_pipeline(**kwargs):
            seen.append(kwargs["task"])
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

        queue = load_queue(queue_path)
        assert [task["status"] for task in queue] == ["cancelled", "skipped", "done"]
        assert seen == ["run me"]
        status = read_status(status_path)
        assert status["queue_cancelled"] == 1
        assert status["queue_skipped"] == 1

    def test_status_tracks_retry_message(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        add_task("retry me", queue_path)

        def mock_pipeline(**kwargs):
            kwargs["on_status"]({
                "type": "retrying",
                "phase": "implementer",
                "retry_count": 1,
                "error": "tests failed",
                "message": "retrying after tester failure",
            })
            return {"phase": "done", "retry_count": 1, "tester_report": ""}

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

        status = read_status(status_path)
        assert status["last_event_type"] == "worker_idle"
        assert status["last_event_message"] == "queue empty"

    def test_status_records_last_finished_time(self, tmp_path):
        queue_path = tmp_path / "q.json"
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        add_task("finish me", queue_path)

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

        status = read_status(status_path)
        assert status["last_task_finished_at"] is not None
        assert status["last_task_id"] is not None
        assert status["last_task_description"] == "finish me"


class TestInteractiveStatus:
    def test_single_task_updates_status_snapshot(self, tmp_path):
        status_path = tmp_path / "status.json"
        tasks_path = tmp_path / "tasks.json"
        sandbox_root = tmp_path / "sandbox"

        with (
            patch("main._STATUS_FILE", status_path),
            patch("main._TASKS_FILE", tasks_path),
            patch("main.SANDBOX", sandbox_root),
            patch("main.print_banner"),
            patch("main.extract_and_save_memory"),
            patch("main.run_pipeline", return_value={"phase": "done", "retry_count": 0, "tester_report": ""}),
        ):
            from main import _run_single_task

            _run_single_task("task-1", "interactive task", "implementer", max_retries=2)

        status = read_status(status_path)
        assert status["worker_state"] == "idle"
        assert status["last_task_id"] == "task-1"
        assert status["last_task_description"] == "interactive task"
        assert status["last_event_type"] == "pipeline_done"
