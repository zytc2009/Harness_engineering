"""File-backed task queue for reliable drain execution."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, TypeVar

_DEFAULT_QUEUE_FILE = Path(__file__).parent / "task_queue.json"
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
_LOCK_SUFFIX = ".lock"
_LOCK_TIMEOUT_S = 5.0
_LOCK_POLL_INTERVAL_S = 0.05

T = TypeVar("T")


class QueueCorruptedError(ValueError):
    """Raised when the queue file exists but cannot be parsed as a valid queue."""


def _now() -> str:
    return datetime.now().strftime(_TS_FORMAT)


def _write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(data, encoding="utf-8")
    tmp_path.replace(path)


def _lock_path(queue_path: str | Path) -> Path:
    path = Path(queue_path)
    return path.with_name(f"{path.name}{_LOCK_SUFFIX}")


def _acquire_lock(queue_path: str | Path) -> Path:
    lock_path = _lock_path(queue_path)
    deadline = time.monotonic() + _LOCK_TIMEOUT_S
    while True:
        try:
            # Simple lockfile protocol: if the process dies abruptly, a stale .lock may
            # remain and force the next writer to time out until it is removed manually.
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for queue lock: {lock_path}")
            time.sleep(_LOCK_POLL_INTERVAL_S)
            continue
        else:
            os.close(fd)
            return lock_path


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _mutate_queue(
    queue_path: str | Path,
    mutator: Callable[[list[dict]], tuple[list[dict], T]],
) -> T:
    lock_path = _acquire_lock(queue_path)
    try:
        tasks = load_queue(queue_path)
        updated_tasks, result = mutator(tasks)
        save_queue(updated_tasks, queue_path)
        return result
    finally:
        _release_lock(lock_path)


def load_queue(queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> list[dict]:
    path = Path(queue_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise QueueCorruptedError(f"Corrupt queue file: {path}") from exc
    if not isinstance(data, list):
        raise QueueCorruptedError(f"Queue file must contain a JSON list: {path}")
    return data


def save_queue(tasks: list[dict], queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> None:
    _write_atomic(Path(queue_path), json.dumps(tasks, ensure_ascii=False, indent=2))


def add_task(
    description: str,
    queue_path: str | Path = _DEFAULT_QUEUE_FILE,
    max_retries: int = 3,
    source_doc: str | None = None,
    source_type: str | None = None,
) -> str:
    def mutator(tasks: list[dict]) -> tuple[list[dict], str]:
        now = _now()
        task_id = str(uuid.uuid4())
        new_task = {
            "id": task_id,
            "description": description,
            "status": "pending",
            "phase": None,
            "retry_count": 0,
            "max_retries": max_retries,
            "error": None,
            "created": now,
            "updated": now,
            "started_at": None,
            "finished_at": None,
            "duration_s": None,
            "source_doc": source_doc,
            "source_type": source_type,
        }
        return [*tasks, new_task], task_id

    return _mutate_queue(queue_path, mutator)


def get_task(task_id: str, queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> dict | None:
    for task in load_queue(queue_path):
        if task.get("id") == task_id:
            return task
    return None


def next_pending(queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> dict | None:
    for task in load_queue(queue_path):
        if task.get("status") == "pending":
            return task
    return None


def update_task(task_id: str, queue_path: str | Path = _DEFAULT_QUEUE_FILE, **fields) -> None:
    def mutator(tasks: list[dict]) -> tuple[list[dict], None]:
        now = _now()
        updated = False
        next_tasks = []
        for task in tasks:
            if task.get("id") == task_id:
                next_tasks.append({**task, **fields, "updated": now})
                updated = True
            else:
                next_tasks.append(task)
        if not updated:
            raise KeyError(f"Task not found: {task_id}")
        return next_tasks, None

    _mutate_queue(queue_path, mutator)


def list_queue(queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> list[dict]:
    return load_queue(queue_path)


def _set_terminal_pending_only(task_id: str, target_status: str, queue_path: str | Path) -> None:
    def mutator(tasks: list[dict]) -> tuple[list[dict], None]:
        now = _now()
        updated = False
        next_tasks = []
        for task in tasks:
            if task.get("id") != task_id:
                next_tasks.append(task)
                continue
            if task.get("status") != "pending":
                raise ValueError(f"Only pending tasks may become {target_status}: {task_id}")
            next_tasks.append({
                **task,
                "status": target_status,
                "finished_at": now,
                "updated": now,
            })
            updated = True
        if not updated:
            raise KeyError(f"Task not found: {task_id}")
        return next_tasks, None

    _mutate_queue(queue_path, mutator)


def cancel_task(task_id: str, queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> None:
    _set_terminal_pending_only(task_id, "cancelled", queue_path)


def skip_task(task_id: str, queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> None:
    _set_terminal_pending_only(task_id, "skipped", queue_path)


def queue_counts(queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> tuple[int, int, int, int, int, int]:
    tasks = load_queue(queue_path)
    pending = sum(1 for task in tasks if task.get("status") == "pending")
    running = sum(1 for task in tasks if task.get("status") == "running")
    done = sum(1 for task in tasks if task.get("status") == "done")
    failed = sum(1 for task in tasks if task.get("status") == "failed")
    cancelled = sum(1 for task in tasks if task.get("status") == "cancelled")
    skipped = sum(1 for task in tasks if task.get("status") == "skipped")
    return pending, running, done, failed, cancelled, skipped


def mark_stale_running_as_failed(queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> int:
    def mutator(tasks: list[dict]) -> tuple[list[dict], int]:
        now = _now()
        changed = 0
        next_tasks = []
        for task in tasks:
            if task.get("status") == "running":
                next_tasks.append({
                    **task,
                    "status": "failed",
                    "error": "worker_interrupted",
                    "finished_at": now,
                    "updated": now,
                })
                changed += 1
            else:
                next_tasks.append(task)
        return next_tasks, changed

    return _mutate_queue(queue_path, mutator)
