"""
Harness Runtime CLI Entry Point
===============================
Supports interactive single-task execution plus queue-backed drain mode.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=Warning, module="requests")

import config
from memory import extract_and_save_memory, load_memories
from orchestrator import SANDBOX, _read_sandbox, architect_phase, run_pipeline
from status import read_status, update_status
from task_queue import (
    add_task as queue_add_task,
    cancel_task,
    list_queue,
    load_queue,
    mark_stale_running_as_failed,
    next_pending,
    queue_counts,
    skip_task,
    update_task as queue_update_task,
)

_TASKS_FILE = Path(__file__).parent / "harness_tasks.json"
_QUEUE_FILE = Path(__file__).parent / "task_queue.json"
_STATUS_FILE = Path(__file__).parent / "status.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(data, encoding="utf-8")
    tmp_path.replace(path)


def _load_tasks() -> list[dict]:
    if not _TASKS_FILE.exists():
        return []
    try:
        data = json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _save_tasks(tasks: list[dict]) -> None:
    _write_atomic(_TASKS_FILE, json.dumps(tasks, ensure_ascii=False, indent=2))


def _upsert_task(thread_id: str, description: str, status: str, **extra) -> None:
    tasks = _load_tasks()
    now = _now()
    for task in tasks:
        if task["id"] == thread_id:
            task["status"] = status
            task["updated"] = now
            task.update(extra)
            _save_tasks(tasks)
            return
    record = {
        "id": thread_id,
        "description": description[:100],
        "status": status,
        "created": now,
        "updated": now,
    }
    record.update(extra)
    tasks.append(record)
    _save_tasks(tasks)


def _incomplete_tasks() -> list[dict]:
    return [task for task in _load_tasks() if task["status"] in ("running", "failed")]


def _task_sandbox_dir(task_id: str) -> Path:
    return SANDBOX / task_id


def _confirm(prompt: str) -> bool:
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("yes", "y"):
            return True
        if answer in ("no", "n"):
            return False
        print("  Please type 'yes' or 'no'.")


def _print_design_preview(sandbox_dir: Path) -> None:
    design = _read_sandbox(sandbox_dir).get("design.md", "")
    if not design:
        return
    lines = design.strip().splitlines()
    preview = "\n  ".join(lines[:20])
    print(f"\n[HARNESS] Architect's plan:\n  {preview}")
    if len(lines) > 20:
        print(f"  ... ({len(lines) - 20} more lines - see design.md in sandbox)")
    print("\n" + "=" * 55)


def _queue_snapshot() -> tuple[int, int, int, int, int, int]:
    return queue_counts(_QUEUE_FILE)


def _write_idle_status() -> None:
    pending, running, done, failed, cancelled, skipped = _queue_snapshot()
    current = read_status(_STATUS_FILE) or {}
    update_status(
        worker_state="idle",
        current_task_id=None,
        current_task_description=None,
        phase=None,
        task_state=None,
        queue_pending=pending,
        queue_running=running,
        queue_done=done,
        queue_failed=failed,
        queue_cancelled=cancelled,
        queue_skipped=skipped,
        last_event_type="worker_idle",
        last_event_message="queue empty",
        last_task_finished_at=current.get("last_task_finished_at"),
        status_path=_STATUS_FILE,
    )


def print_banner(thread_id: str, sandbox_dir: Path | None = None) -> None:
    print("=" * 55)
    print("  Harness Runtime - Pipeline")
    for phase in ("architect", "implementer", "tester"):
        provider = config._resolve_provider(phase)
        model = config._resolve_model(phase)
        print(f"  {phase.capitalize():<12}: {provider} / {model}")
    if sandbox_dir is None:
        sandbox_dir = _task_sandbox_dir(thread_id)
    print(f"  Sandbox      : {sandbox_dir}")
    print(f"  Task ID      : {thread_id}")
    print("=" * 55)


def list_tasks() -> None:
    tasks = _load_tasks()
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


def handle_add(description: str, max_retries: int = 3) -> str:
    task_id = queue_add_task(description, _QUEUE_FILE, max_retries=max_retries)
    print(f"[HARNESS] Task added: {task_id}")
    print(f"  Description: {description}")
    print("  Run 'python main.py --drain' to process queued tasks.")
    return task_id


def handle_cancel(task_id: str) -> None:
    cancel_task(task_id, _QUEUE_FILE)
    print(f"[HARNESS] Task cancelled: {task_id}")
    pending, running, done, failed, cancelled, skipped = _queue_snapshot()
    update_status(
        worker_state="idle",
        current_task_id=None,
        current_task_description=None,
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
        status_path=_STATUS_FILE,
    )


def handle_skip(task_id: str) -> None:
    skip_task(task_id, _QUEUE_FILE)
    print(f"[HARNESS] Task skipped: {task_id}")
    pending, running, done, failed, cancelled, skipped = _queue_snapshot()
    update_status(
        worker_state="idle",
        current_task_id=None,
        current_task_description=None,
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
        status_path=_STATUS_FILE,
    )


def show_status() -> None:
    data = read_status(_STATUS_FILE)
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
    print(
        f"  Queue       : {data.get('queue_pending', 0)} pending, "
        f"{data.get('queue_running', 0)} running, "
        f"{data.get('queue_done', 0)} done, "
        f"{data.get('queue_failed', 0)} failed, "
        f"{data.get('queue_cancelled', 0)} cancelled, "
        f"{data.get('queue_skipped', 0)} skipped"
    )
    if data.get("error"):
        print(f"  Error       : {data['error']}")
    print(f"  Updated     : {data.get('updated', '-')}")
    print("=" * 55 + "\n")


def _print_queue() -> None:
    queue = list_queue(_QUEUE_FILE)
    if not queue:
        print("[HARNESS] Queue is empty.")
        return
    print(f"\n{'ID':<36}  {'Status':<10}  {'Created':<19}  Description")
    print("-" * 110)
    for task in queue:
        print(f"{task['id']}  {task['status']:<10}  {task['created']:<19}  {task['description'][:60]}")
    print()


def _save_memory_if_present(user_input: str, tester_report: str) -> None:
    if not tester_report:
        return
    print("\n[HARNESS] Extracting long-term memory...")
    from langchain_core.messages import AIMessage, HumanMessage

    messages = [HumanMessage(content=user_input), AIMessage(content=tester_report)]
    summary = extract_and_save_memory(messages, user_input)
    print(f"[HARNESS] Memory saved: {summary}\n")


def _status_callback_for_task(thread_id: str, description: str, max_retries: int):
    def callback(event: dict) -> None:
        pending, running, done, failed, cancelled, skipped = _queue_snapshot()
        event_type = event.get("type")
        phase = event.get("phase")
        retry_count = event.get("retry_count", 0)
        error = event.get("error")
        message = event.get("message")

        worker_state = "running"
        task_state = "running"
        if event_type == "pipeline_done":
            task_state = "done"
        elif event_type == "pipeline_failed":
            task_state = "failed"
        elif event_type == "pipeline_cancelled":
            worker_state = "stopped"
            task_state = "failed"

        update_status(
            worker_state=worker_state,
            current_task_id=thread_id,
            current_task_description=description,
            phase=phase,
            task_state=task_state,
            retry_count=retry_count,
            max_retries=max_retries,
            queue_pending=pending,
            queue_running=running,
            queue_done=done,
            queue_failed=failed,
            queue_cancelled=cancelled,
            queue_skipped=skipped,
            last_event_type=event_type,
            last_event_message=message,
            error=error,
            status_path=_STATUS_FILE,
        )

    return callback


def run_drain(max_retries: int = 3) -> None:
    config.validate()
    repaired = mark_stale_running_as_failed(_QUEUE_FILE)
    if repaired:
        print(f"[HARNESS] Recovered {repaired} interrupted running task(s).")

    while True:
        task = next_pending(_QUEUE_FILE)
        if task is None:
            _write_idle_status()
            print("\n[HARNESS] Queue empty. Drain finished.")
            return

        thread_id = task["id"]
        user_input = task["description"]
        sandbox_dir = _task_sandbox_dir(thread_id)
        print_banner(thread_id, sandbox_dir)

        queue_update_task(
            thread_id,
            queue_path=_QUEUE_FILE,
            status="running",
            phase="architect",
            started_at=task.get("started_at") or _now(),
            error=None,
            max_retries=max_retries,
        )
        _upsert_task(thread_id, user_input, "running", phase="architect", retry_count=0)
        callback = _status_callback_for_task(thread_id, user_input, max_retries)
        callback({
            "type": "phase_started",
            "phase": "architect",
            "retry_count": 0,
            "error": None,
            "message": "architect started",
        })

        started = time.monotonic()
        try:
            result = run_pipeline(
                task=user_input,
                start_phase="architect",
                max_retries=max_retries,
                sandbox_dir=sandbox_dir,
                on_status=callback,
            )
        except KeyboardInterrupt:
            duration = round(time.monotonic() - started, 1)
            queue_update_task(
                thread_id,
                queue_path=_QUEUE_FILE,
                status="failed",
                phase="interrupted",
                error="interrupted",
                duration_s=duration,
                finished_at=_now(),
            )
            _upsert_task(
                thread_id,
                user_input,
                "failed",
                phase="interrupted",
                duration_s=duration,
                error="interrupted",
            )
            pending, running, done, failed, cancelled, skipped = _queue_snapshot()
            update_status(
                worker_state="stopped",
                current_task_id=thread_id,
                current_task_description=user_input,
                phase="interrupted",
                task_state="failed",
                retry_count=0,
                max_retries=max_retries,
                queue_pending=pending,
                queue_running=running,
                queue_done=done,
                queue_failed=failed,
                queue_cancelled=cancelled,
                queue_skipped=skipped,
                last_event_type="pipeline_interrupted",
                last_event_message="worker interrupted during task execution",
                error="interrupted",
                status_path=_STATUS_FILE,
            )
            print("\n[HARNESS] Interrupted. Remaining pending tasks were left untouched.")
            return
        except Exception as exc:
            duration = round(time.monotonic() - started, 1)
            queue_update_task(
                thread_id,
                queue_path=_QUEUE_FILE,
                status="failed",
                phase="error",
                error=str(exc)[:200],
                duration_s=duration,
                finished_at=_now(),
            )
            _upsert_task(
                thread_id,
                user_input,
                "failed",
                phase="error",
                duration_s=duration,
                error=str(exc)[:200],
            )
            print(f"\n[HARNESS] Task failed: {exc}")
            print("[HARNESS] Moving to next task...")
            continue

        duration = round(time.monotonic() - started, 1)
        failed = bool(result.get("failed"))
        final_status = "failed" if failed else "done"
        final_error = "tests_failed" if failed else None
        finished_at = _now()

        queue_update_task(
            thread_id,
            queue_path=_QUEUE_FILE,
            status=final_status,
            phase=result["phase"],
            retry_count=result["retry_count"],
            duration_s=duration,
            finished_at=finished_at,
            error=final_error,
        )
        _upsert_task(
            thread_id,
            user_input,
            final_status,
            phase=result["phase"],
            retry_count=result["retry_count"],
            duration_s=duration,
            **({"error": final_error} if final_error else {}),
        )
        pending, running, done, failed_count, cancelled, skipped = _queue_snapshot()
        update_status(
            worker_state="running",
            current_task_id=thread_id,
            current_task_description=user_input,
            phase=result["phase"],
            task_state=final_status,
            retry_count=result["retry_count"],
            max_retries=max_retries,
            queue_pending=pending,
            queue_running=running,
            queue_done=done,
            queue_failed=failed_count,
            queue_cancelled=cancelled,
            queue_skipped=skipped,
            last_event_type="pipeline_failed" if failed else "pipeline_done",
            last_event_message="task failed after retries" if failed else "task completed",
            last_task_finished_at=finished_at,
            error=final_error,
            status_path=_STATUS_FILE,
        )

        _save_memory_if_present(user_input, result.get("tester_report", ""))
        print(f"[HARNESS] Task {final_status}: {thread_id}")
        if failed:
            print("[HARNESS] Moving to next task...")


def _choose_interactive_task() -> tuple[str, str, str]:
    thread_id: str
    user_input: str
    start_phase = "architect"

    incomplete = _incomplete_tasks()
    if incomplete:
        print(f"\n[HARNESS] Found {len(incomplete)} incomplete task(s):")
        for index, task in enumerate(incomplete, 1):
            print(f"  [{index}] {task['id'][:8]}...  {task['updated']}  {task['description']}")
        print("  [N] Start a new task")
        choice = input("\nResume which? (1/2/.../N): ").strip().upper()
        if choice.isdigit() and 1 <= int(choice) <= len(incomplete):
            picked = incomplete[int(choice) - 1]
            print(f"\n[HARNESS] Resuming: {picked['description']}")
            return picked["id"], picked["description"], "implementer"

    thread_id = str(uuid.uuid4())
    memories = load_memories()
    if memories:
        print(f"[HARNESS] Found {len(memories)} memory record(s).")
        print(f"          Last: {memories[-1]['date']} - {memories[-1]['summary'][:60]}...")
    else:
        print("[HARNESS] No long-term memory found. Starting fresh.")
    print("\nDescribe your task:")
    user_input = input("Task: ").strip()
    return thread_id, user_input, start_phase


def _run_single_task(thread_id: str, user_input: str, start_phase: str, max_retries: int) -> None:
    sandbox_dir = _task_sandbox_dir(thread_id)
    print_banner(thread_id, sandbox_dir)
    _upsert_task(thread_id, user_input, "running", phase=start_phase, retry_count=0)

    if start_phase == "architect":
        design = architect_phase(user_input, sandbox_dir=sandbox_dir)
        _print_design_preview(sandbox_dir)
        if not _confirm("  Proceed with implementation? (yes/no): "):
            print("  [HARNESS] Implementation cancelled.")
            _upsert_task(thread_id, user_input, "failed", phase="cancelled", error="cancelled")
            return
        start_phase = "implementer"

    started = time.monotonic()
    print("\n[HARNESS] Starting pipeline...\n")
    try:
        result = run_pipeline(
            task=user_input,
            start_phase=start_phase,
            max_retries=max_retries,
            sandbox_dir=sandbox_dir,
        )
    except KeyboardInterrupt:
        duration = round(time.monotonic() - started, 1)
        print("\n\n[HARNESS] Interrupted.")
        _upsert_task(
            thread_id,
            user_input,
            "failed",
            phase="interrupted",
            duration_s=duration,
            error="KeyboardInterrupt",
        )
        print(f"[HARNESS] Resume with: python main.py --resume {thread_id}\n")
        return
    except Exception as exc:
        duration = round(time.monotonic() - started, 1)
        print(f"\n[HARNESS] Error: {exc}")
        _upsert_task(thread_id, user_input, "failed", duration_s=duration, error=str(exc)[:200])
        raise

    duration = round(time.monotonic() - started, 1)
    print("\n" + "=" * 55)
    print("  FINAL RESPONSE")
    print("=" * 55)
    if result.get("failed"):
        print("Tests did not pass after all retries.")
    elif result["phase"] == "cancelled":
        print("Task cancelled by user.")
    else:
        print("Pipeline complete.")

    report = result.get("tester_report", "")
    if report:
        print("\nTester report:")
        print(report[:800])

    sandbox_files = _read_sandbox(sandbox_dir)
    if sandbox_files:
        print(f"\nFiles in sandbox ({len(sandbox_files)}):")
        for name in sorted(sandbox_files):
            print(f"  {name}")
    print(f"\nSandbox path: {sandbox_dir}")
    print("=" * 55)
    print(f"  Phase     : {result['phase']}")
    print(f"  Retries   : {result['retry_count']}/{max_retries}")
    print(f"  Duration  : {duration}s")
    print("=" * 55)

    status = "failed" if result.get("failed") else "done"
    _upsert_task(
        thread_id,
        user_input,
        status,
        phase=result["phase"],
        retry_count=result["retry_count"],
        duration_s=duration,
        **({"error": "tests_failed"} if result.get("failed") else {}),
    )
    _save_memory_if_present(user_input, report)
    print(f"[HARNESS] Task ID: {thread_id}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harness Runtime - Queue and Pipeline")
    parser.add_argument("--resume", metavar="ID", help="Restart a saved task")
    parser.add_argument("--list", action="store_true", help="List all saved tasks")
    parser.add_argument("--add", metavar="DESC", help="Add a task to the queue")
    parser.add_argument("--cancel", metavar="ID", help="Cancel a pending queued task")
    parser.add_argument("--skip", metavar="ID", help="Skip a pending queued task")
    parser.add_argument("--queue", action="store_true", help="List queued tasks")
    parser.add_argument("--status", action="store_true", help="Show current worker status")
    parser.add_argument("--drain", action="store_true", help="Process all pending queue tasks and exit")
    parser.add_argument(
        "--phase",
        default="architect",
        choices=["architect", "implementer", "tester"],
        help="Starting phase (default: architect)",
    )
    args = parser.parse_args()

    if args.list:
        list_tasks()
        return
    if args.add:
        max_retries = int(config.get_setting("MAX_RETRIES", "3"))
        handle_add(args.add, max_retries=max_retries)
        return
    if args.cancel:
        handle_cancel(args.cancel)
        return
    if args.skip:
        handle_skip(args.skip)
        return
    if args.queue:
        _print_queue()
        return
    if args.status:
        show_status()
        return
    if args.drain:
        max_retries = int(config.get_setting("MAX_RETRIES", "3"))
        run_drain(max_retries=max_retries)
        return

    config.validate()
    max_retries = int(config.get_setting("MAX_RETRIES", "3"))

    if args.resume:
        tasks = _load_tasks()
        match = next((task for task in tasks if task["id"] == args.resume), None)
        if not match:
            print(f"[ERROR] Thread '{args.resume}' not found. Use --list to see saved tasks.")
            sys.exit(1)
        print(f"\n[HARNESS] Resuming task: {match['description']}")
        _run_single_task(args.resume, match["description"], "implementer", max_retries)
        return

    thread_id, user_input, start_phase = _choose_interactive_task()
    if not user_input:
        print("No task provided. Exiting.")
        return
    _run_single_task(thread_id, user_input, start_phase, max_retries)


if __name__ == "__main__":
    main()
