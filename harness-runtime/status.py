"""Worker status snapshot helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

_DEFAULT_STATUS_FILE = Path(__file__).parent / "task" / "status.json"
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
logger = logging.getLogger(__name__)


def _write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(data, encoding="utf-8")
    tmp_path.replace(path)


def update_status(
    *,
    worker_state: str,
    current_task_id: str | None,
    current_task_description: str | None,
    last_task_id: str | None = None,
    last_task_description: str | None = None,
    phase: str | None,
    task_state: str | None,
    retry_count: int = 0,
    max_retries: int = 3,
    subtask_id: int | None = None,
    subtask_total: int | None = None,
    queue_pending: int = 0,
    queue_running: int = 0,
    queue_done: int = 0,
    queue_failed: int = 0,
    queue_cancelled: int = 0,
    queue_skipped: int = 0,
    last_event_type: str | None = None,
    last_event_message: str | None = None,
    last_task_finished_at: str | None = None,
    error: str | None = None,
    status_path: str | Path = _DEFAULT_STATUS_FILE,
) -> None:
    data = {
        "worker_state": worker_state,
        "current_task_id": current_task_id,
        "current_task_description": current_task_description,
        "last_task_id": last_task_id,
        "last_task_description": last_task_description,
        "phase": phase,
        "task_state": task_state,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "subtask_id": subtask_id,
        "subtask_total": subtask_total,
        "queue_pending": queue_pending,
        "queue_running": queue_running,
        "queue_done": queue_done,
        "queue_failed": queue_failed,
        "queue_cancelled": queue_cancelled,
        "queue_skipped": queue_skipped,
        "last_event_type": last_event_type,
        "last_event_message": last_event_message,
        "last_task_finished_at": last_task_finished_at,
        "error": error,
        "updated": datetime.now().strftime(_TS_FORMAT),
    }
    _write_atomic(Path(status_path), json.dumps(data, ensure_ascii=False, indent=2))


def read_status(status_path: str | Path = _DEFAULT_STATUS_FILE) -> dict | None:
    path = Path(status_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse status file %s: %s", path, exc)
        return None
    except OSError as exc:
        logger.debug("Failed to read status file %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None
