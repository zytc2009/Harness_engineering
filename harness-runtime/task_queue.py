"""File-backed task queue for reliable drain execution."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

_DEFAULT_QUEUE_FILE = Path(__file__).parent / "task_queue.json"
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


class QueueCorruptedError(ValueError):
    """Raised when the queue file exists but cannot be parsed as a valid queue."""


def _now() -> str:
    return datetime.now().strftime(_TS_FORMAT)


def _write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(data, encoding="utf-8")
    tmp_path.replace(path)


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
) -> str:
    tasks = load_queue(queue_path)
    now = _now()
    task_id = str(uuid.uuid4())
    tasks.append({
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
    })
    save_queue(tasks, queue_path)
    return task_id


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
    tasks = load_queue(queue_path)
    for task in tasks:
        if task.get("id") == task_id:
            task.update(fields)
            task["updated"] = _now()
            save_queue(tasks, queue_path)
            return
    raise KeyError(f"Task not found: {task_id}")


def list_queue(queue_path: str | Path = _DEFAULT_QUEUE_FILE) -> list[dict]:
    return load_queue(queue_path)


def _set_terminal_pending_only(task_id: str, target_status: str, queue_path: str | Path) -> None:
    tasks = load_queue(queue_path)
    now = _now()
    for task in tasks:
        if task.get("id") != task_id:
            continue
        if task.get("status") != "pending":
            raise ValueError(f"Only pending tasks may become {target_status}: {task_id}")
        task["status"] = target_status
        task["finished_at"] = now
        task["updated"] = now
        save_queue(tasks, queue_path)
        return
    raise KeyError(f"Task not found: {task_id}")


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
    tasks = load_queue(queue_path)
    now = _now()
    changed = 0
    for task in tasks:
        if task.get("status") == "running":
            task["status"] = "failed"
            task["error"] = "worker_interrupted"
            task["finished_at"] = now
            task["updated"] = now
            changed += 1
    if changed:
        save_queue(tasks, queue_path)
    return changed
