"""Tests for task_queue module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from task_queue import (
    QueueCorruptedError,
    add_task,
    get_task,
    list_queue,
    load_queue,
    mark_stale_running_as_failed,
    next_pending,
    queue_counts,
    save_queue,
    update_task,
)


class TestLoadSaveQueue:
    def test_load_returns_empty_when_no_file(self, tmp_path):
        path = tmp_path / "q.json"
        assert load_queue(path) == []

    def test_load_raises_on_corrupt_file(self, tmp_path):
        path = tmp_path / "q.json"
        path.write_text("{bad json", encoding="utf-8")
        with pytest.raises(QueueCorruptedError):
            load_queue(path)

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "q.json"
        tasks = [{
            "id": "1",
            "description": "test",
            "status": "pending",
            "phase": None,
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "created": "2026-04-10 10:00:00",
            "updated": "2026-04-10 10:00:00",
            "started_at": None,
            "finished_at": None,
            "duration_s": None,
        }]
        save_queue(tasks, path)
        assert load_queue(path) == tasks


class TestAddTask:
    def test_adds_task_with_pending_status(self, tmp_path):
        path = tmp_path / "q.json"
        task_id = add_task("build calculator", path)
        queue = load_queue(path)
        assert len(queue) == 1
        assert queue[0]["id"] == task_id
        assert queue[0]["description"] == "build calculator"
        assert queue[0]["status"] == "pending"
        assert queue[0]["max_retries"] == 3

    def test_appends_to_existing_queue_in_fifo_order(self, tmp_path):
        path = tmp_path / "q.json"
        add_task("task 1", path)
        add_task("task 2", path)
        queue = load_queue(path)
        assert [task["description"] for task in queue] == ["task 1", "task 2"]


class TestSelectorsAndCounts:
    def test_get_task_returns_match(self, tmp_path):
        path = tmp_path / "q.json"
        task_id = add_task("task 1", path)
        assert get_task(task_id, path)["description"] == "task 1"

    def test_next_pending_returns_none_when_empty(self, tmp_path):
        path = tmp_path / "q.json"
        assert next_pending(path) is None

    def test_next_pending_returns_first_pending(self, tmp_path):
        path = tmp_path / "q.json"
        add_task("first", path)
        add_task("second", path)
        task = next_pending(path)
        assert task["description"] == "first"

    def test_next_pending_skips_non_pending(self, tmp_path):
        path = tmp_path / "q.json"
        first_id = add_task("done task", path)
        add_task("pending task", path)
        update_task(first_id, queue_path=path, status="done")
        task = next_pending(path)
        assert task["description"] == "pending task"

    def test_queue_counts(self, tmp_path):
        path = tmp_path / "q.json"
        a = add_task("a", path)
        b = add_task("b", path)
        update_task(a, queue_path=path, status="running")
        update_task(b, queue_path=path, status="done")
        assert queue_counts(path) == (0, 1, 1, 0)


class TestUpdateTask:
    def test_updates_fields_and_timestamp(self, tmp_path):
        path = tmp_path / "q.json"
        task_id = add_task("task", path)
        before = load_queue(path)[0]["updated"]
        update_task(task_id, queue_path=path, status="running", retry_count=1)
        task = load_queue(path)[0]
        assert task["status"] == "running"
        assert task["retry_count"] == 1
        assert task["updated"] >= before

    def test_raises_on_unknown_id(self, tmp_path):
        path = tmp_path / "q.json"
        with pytest.raises(KeyError):
            update_task("nonexistent", queue_path=path, status="done")


class TestRecovery:
    def test_mark_stale_running_as_failed(self, tmp_path):
        path = tmp_path / "q.json"
        running_id = add_task("running", path)
        add_task("pending", path)
        update_task(running_id, queue_path=path, status="running")

        changed = mark_stale_running_as_failed(path)

        queue = load_queue(path)
        assert changed == 1
        assert queue[0]["status"] == "failed"
        assert queue[0]["error"] == "worker_interrupted"
        assert queue[0]["finished_at"] is not None


class TestListQueue:
    def test_returns_all_tasks(self, tmp_path):
        path = tmp_path / "q.json"
        add_task("a", path)
        add_task("b", path)
        assert len(list_queue(path)) == 2
