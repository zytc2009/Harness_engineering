"""Queue-oriented CLI actions."""

from __future__ import annotations

import json
from pathlib import Path

from status import read_status, update_status
from task_doc import load_task_doc
from task_queue import add_task as queue_add_task
from task_queue import cancel_task, list_queue, load_queue, skip_task

from runtime_support import last_task_snapshot, queue_snapshot


def list_tasks(queue_file: Path) -> None:
    tasks = load_queue(queue_file)
    if not tasks:
        print("No saved tasks.")
        return
    print(f"\n{'ID':<36}  {'Status':<10}  {'Phase':<12}  {'Retries':<7}  {'Duration':>8}  {'Updated':<19}  Description")
    print("-" * 120)
    for task in reversed(tasks):
        phase = task.get("phase", "-")
        retries = str(task.get("retry_count", "-"))
        duration = task.get("duration_s")
        duration_str = f"{duration}s" if duration is not None else "-"
        error = f"  ! {task['error']}" if task.get("error") else ""
        print(
            f"{task['id']}  {task['status']:<10}  {phase:<12}  {retries:<7}  {duration_str:>8}  "
            f"{task['updated']:<19}  {task['description']}{error}"
        )
    print()


def handle_add(description: str, max_retries: int, queue_file: Path, status_file: Path) -> str:
    task_id = queue_add_task(description, queue_file, max_retries=max_retries)
    pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
    last_task_id, last_task_description, last_task_finished_at = last_task_snapshot(status_file)
    update_status(
        worker_state="idle",
        current_task_id=None,
        current_task_description=None,
        last_task_id=last_task_id,
        last_task_description=last_task_description,
        phase=None,
        task_state=None,
        queue_pending=pending,
        queue_running=running,
        queue_done=done,
        queue_failed=failed,
        queue_cancelled=cancelled,
        queue_skipped=skipped,
        last_event_type="task_queued",
        last_event_message=f"task queued: {task_id}",
        last_task_finished_at=last_task_finished_at,
        status_path=status_file,
    )
    print(f"[HARNESS] Task added: {task_id}")
    print(f"  Description: {description}")
    print("  Run 'python main.py --drain' to process queued tasks.")
    return task_id


def handle_add_file(doc_path: str, max_retries: int, queue_file: Path, status_file: Path) -> str:
    resolved_doc_path, description, constraints = load_task_doc(doc_path)
    task_id = queue_add_task(
        description,
        queue_file,
        max_retries=max_retries,
        source_doc=str(resolved_doc_path),
        source_type="task_doc",
        constraints=constraints,
    )
    pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
    last_task_id, last_task_description, last_task_finished_at = last_task_snapshot(status_file)
    update_status(
        worker_state="idle",
        current_task_id=None,
        current_task_description=None,
        last_task_id=last_task_id,
        last_task_description=last_task_description,
        phase=None,
        task_state=None,
        queue_pending=pending,
        queue_running=running,
        queue_done=done,
        queue_failed=failed,
        queue_cancelled=cancelled,
        queue_skipped=skipped,
        last_event_type="task_queued",
        last_event_message=f"task queued from doc: {task_id}",
        last_task_finished_at=last_task_finished_at,
        status_path=status_file,
    )
    print(f"[HARNESS] Task added from doc: {task_id}")
    print(f"  Source: {resolved_doc_path}")
    print("  Run 'python main.py --drain' to process queued tasks.")
    return task_id


def handle_cancel(task_id: str, queue_file: Path, status_file: Path) -> None:
    cancel_task(task_id, queue_file)
    print(f"[HARNESS] Task cancelled: {task_id}")
    pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
    last_task_id, last_task_description, last_task_finished_at = last_task_snapshot(status_file)
    update_status(
        worker_state="idle",
        current_task_id=None,
        current_task_description=None,
        last_task_id=last_task_id,
        last_task_description=last_task_description,
        phase=None,
        task_state=None,
        queue_pending=pending,
        queue_running=running,
        queue_done=done,
        queue_failed=failed,
        queue_cancelled=cancelled,
        queue_skipped=skipped,
        last_event_type="task_cancelled",
        last_event_message=f"task cancelled: {task_id}",
        last_task_finished_at=last_task_finished_at,
        status_path=status_file,
    )


def handle_skip(task_id: str, queue_file: Path, status_file: Path) -> None:
    skip_task(task_id, queue_file)
    print(f"[HARNESS] Task skipped: {task_id}")
    pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
    last_task_id, last_task_description, last_task_finished_at = last_task_snapshot(status_file)
    update_status(
        worker_state="idle",
        current_task_id=None,
        current_task_description=None,
        last_task_id=last_task_id,
        last_task_description=last_task_description,
        phase=None,
        task_state=None,
        queue_pending=pending,
        queue_running=running,
        queue_done=done,
        queue_failed=failed,
        queue_cancelled=cancelled,
        queue_skipped=skipped,
        last_event_type="task_skipped",
        last_event_message=f"task skipped: {task_id}",
        last_task_finished_at=last_task_finished_at,
        status_path=status_file,
    )


def show_status(status_file: Path) -> None:
    data = read_status(status_file)
    if data is None:
        print("[HARNESS] No status available. Worker has not run yet.")
        return
    print("\n" + "=" * 55)
    print("  HARNESS STATUS")
    print("=" * 55)
    print(f"  Worker      : {data.get('worker_state', 'unknown')}")
    print(f"  Task State  : {data.get('task_state', '-')}")
    if data.get("current_task_id"):
        print(f"  Task ID     : {data['current_task_id']}")
        print(f"  Description : {data.get('current_task_description', '-')}")
        print(f"  Phase       : {data.get('phase', '-')}")
        print(f"  Retries     : {data.get('retry_count', 0)}/{data.get('max_retries', 3)}")
    elif data.get("last_task_id"):
        print(f"  Last Task   : {data['last_task_id']}")
        print(f"  Last Desc   : {data.get('last_task_description', '-')}")
        print(f"  Last Done   : {data.get('last_task_finished_at', '-')}")
    print(
        f"  Queue       : {data.get('queue_pending', 0)} pending, "
        f"{data.get('queue_running', 0)} running, "
        f"{data.get('queue_done', 0)} done, "
        f"{data.get('queue_failed', 0)} failed, "
        f"{data.get('queue_cancelled', 0)} cancelled, "
        f"{data.get('queue_skipped', 0)} skipped"
    )
    if data.get("last_event_type"):
        print(f"  Last Event  : {data['last_event_type']}")
    if data.get("last_event_message"):
        print(f"  Event Msg   : {data['last_event_message']}")
    if data.get("error"):
        print(f"  Error       : {data['error']}")
    print(f"  Updated     : {data.get('updated', '-')}")
    print("=" * 55 + "\n")


def show_status_json(status_file: Path) -> None:
    data = read_status(status_file)
    payload = data if data is not None else {"status": "unavailable"}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def print_queue(queue_file: Path) -> None:
    queue = list_queue(queue_file)
    if not queue:
        print("[HARNESS] Queue is empty.")
        return
    print(f"\n{'ID':<36}  {'Status':<10}  {'Created':<19}  Description")
    print("-" * 110)
    for task in queue:
        source = f"  [{Path(task['source_doc']).name}]" if task.get("source_doc") else ""
        print(f"{task['id']}  {task['status']:<10}  {task['created']:<19}  {task['description'][:60]}{source}")
    print()


def print_queue_json(queue_file: Path) -> None:
    print(json.dumps(list_queue(queue_file), ensure_ascii=False, indent=2))
