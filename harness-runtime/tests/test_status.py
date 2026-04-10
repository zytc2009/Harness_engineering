"""Tests for status module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from status import read_status, update_status


class TestUpdateStatus:
    def test_writes_idle_status(self, tmp_path):
        path = tmp_path / "status.json"
        update_status(
            worker_state="idle",
            current_task_id=None,
            current_task_description=None,
            phase=None,
            task_state=None,
            status_path=path,
        )
        data = read_status(path)
        assert data["worker_state"] == "idle"
        assert data["current_task_id"] is None

    def test_writes_running_status_with_queue_counts(self, tmp_path):
        path = tmp_path / "status.json"
        update_status(
            worker_state="running",
            current_task_id="abc-123",
            current_task_description="build calc",
            last_task_id="prev-1",
            last_task_description="previous task",
            phase="architect",
            task_state="running",
            retry_count=1,
            max_retries=3,
            queue_pending=2,
            queue_running=1,
            queue_done=4,
            queue_failed=1,
            queue_cancelled=2,
            queue_skipped=3,
            last_event_type="phase_started",
            last_event_message="architect started",
            last_task_finished_at="2026-04-10 10:05:00",
            error="boom",
            status_path=path,
        )
        data = read_status(path)
        assert data["worker_state"] == "running"
        assert data["current_task_id"] == "abc-123"
        assert data["last_task_id"] == "prev-1"
        assert data["last_task_description"] == "previous task"
        assert data["queue_pending"] == 2
        assert data["queue_running"] == 1
        assert data["queue_done"] == 4
        assert data["queue_failed"] == 1
        assert data["queue_cancelled"] == 2
        assert data["queue_skipped"] == 3
        assert data["last_event_type"] == "phase_started"
        assert data["last_event_message"] == "architect started"
        assert data["last_task_finished_at"] == "2026-04-10 10:05:00"
        assert data["error"] == "boom"


class TestReadStatus:
    def test_returns_none_when_no_file(self, tmp_path):
        path = tmp_path / "status.json"
        assert read_status(path) is None

    def test_returns_none_on_corrupt_file(self, tmp_path):
        path = tmp_path / "status.json"
        path.write_text("{bad", encoding="utf-8")
        assert read_status(path) is None
