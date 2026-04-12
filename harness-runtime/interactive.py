"""Interactive single-task runtime flow."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import execution
from memory import load_memories
from orchestrator import SANDBOX, _read_sandbox, architect_phase, run_pipeline
from status import update_status
from task_queue import load_queue

from runtime_support import (
    confirm,
    last_task_snapshot,
    monotonic_duration,
    now_str,
    print_banner,
    print_design_preview,
    queue_snapshot,
    queue_upsert_execution_task,
    save_memory_if_present,
    task_sandbox_dir,
)


def incomplete_tasks(queue_file: Path) -> list[dict]:
    return [task for task in load_queue(queue_file) if task.get("status") in ("running", "failed")]


def choose_interactive_task(queue_file: Path) -> tuple[str, str, str]:
    thread_id: str
    user_input: str
    start_phase = "architect"

    incomplete = incomplete_tasks(queue_file)
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


def run_single_task(
    thread_id: str,
    user_input: str,
    start_phase: str,
    max_retries: int,
    queue_file: Path,
    status_file: Path,
    sandbox_root: Path = SANDBOX,
) -> None:
    run_single_task_with_hooks(
        thread_id,
        user_input,
        start_phase,
        max_retries,
        queue_file,
        status_file,
        sandbox_root=sandbox_root,
    )


def run_single_task_with_hooks(
    thread_id: str,
    user_input: str,
    start_phase: str,
    max_retries: int,
    queue_file: Path,
    status_file: Path,
    *,
    sandbox_root: Path = SANDBOX,
    print_banner_fn=print_banner,
    architect_phase_fn=architect_phase,
    run_pipeline_fn=run_pipeline,
    print_design_preview_fn=print_design_preview,
    confirm_fn=confirm,
    save_memory_if_present_fn=save_memory_if_present,
) -> None:
    sandbox_dir = task_sandbox_dir(thread_id, sandbox_root)
    task_metadata = {"constraints": {}}
    execution.validate_runtime(task_metadata=task_metadata)
    print_banner_fn(thread_id, sandbox_dir, task_metadata=task_metadata)
    queue_upsert_execution_task(
        queue_file,
        thread_id,
        user_input,
        "running",
        phase=start_phase,
        retry_count=0,
        started_at=now_str(),
        max_retries=max_retries,
    )
    pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
    last_task_id, last_task_description, last_task_finished_at = last_task_snapshot(status_file)
    update_status(
        worker_state="running",
        current_task_id=thread_id,
        current_task_description=user_input,
        last_task_id=last_task_id,
        last_task_description=last_task_description,
        phase=start_phase,
        task_state="running",
        retry_count=0,
        max_retries=max_retries,
        queue_pending=pending,
        queue_running=running,
        queue_done=done,
        queue_failed=failed,
        queue_cancelled=cancelled,
        queue_skipped=skipped,
        last_event_type="phase_started",
        last_event_message=f"{start_phase} started",
        last_task_finished_at=last_task_finished_at,
        status_path=status_file,
    )

    started = time.monotonic()
    try:
        if start_phase == "architect":
            architect_phase_fn(user_input, sandbox_dir=sandbox_dir, task_metadata=task_metadata)
            print_design_preview_fn(sandbox_dir)
            if not confirm_fn("  Proceed with implementation? (yes/no): "):
                print("  [HARNESS] Implementation cancelled.")
                queue_upsert_execution_task(queue_file, thread_id, user_input, "failed", phase="cancelled", error="cancelled")
                pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
                update_status(
                    worker_state="stopped",
                    current_task_id=thread_id,
                    current_task_description=user_input,
                    last_task_id=last_task_id,
                    last_task_description=last_task_description,
                    phase="cancelled",
                    task_state="failed",
                    retry_count=0,
                    max_retries=max_retries,
                    queue_pending=pending,
                    queue_running=running,
                    queue_done=done,
                    queue_failed=failed,
                    queue_cancelled=cancelled,
                    queue_skipped=skipped,
                    last_event_type="pipeline_cancelled",
                    last_event_message="interactive task cancelled before implementation",
                    last_task_finished_at=last_task_finished_at,
                    error="cancelled",
                    status_path=status_file,
                )
                return
            start_phase = "implementer"

        print("\n[HARNESS] Starting pipeline...\n")
        result = run_pipeline_fn(
            task=user_input,
            start_phase=start_phase,
            max_retries=max_retries,
            sandbox_dir=sandbox_dir,
            task_metadata=task_metadata,
        )
    except KeyboardInterrupt:
        duration = monotonic_duration(started)
        print("\n\n[HARNESS] Interrupted.")
        queue_upsert_execution_task(
            queue_file,
            thread_id,
            user_input,
            "failed",
            phase="interrupted",
            duration_s=duration,
            error="KeyboardInterrupt",
        )
        pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
        update_status(
            worker_state="stopped",
            current_task_id=thread_id,
            current_task_description=user_input,
            last_task_id=thread_id,
            last_task_description=user_input,
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
            last_event_message="interactive task interrupted",
            last_task_finished_at=now_str(),
            error="KeyboardInterrupt",
            status_path=status_file,
        )
        print(f"[HARNESS] Resume with: python main.py --resume {thread_id}\n")
        return
    except Exception as exc:
        duration = monotonic_duration(started)
        print(f"\n[HARNESS] Error: {exc}")
        queue_upsert_execution_task(queue_file, thread_id, user_input, "failed", duration_s=duration, error=str(exc)[:200])
        pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
        update_status(
            worker_state="stopped",
            current_task_id=thread_id,
            current_task_description=user_input,
            last_task_id=thread_id,
            last_task_description=user_input,
            phase="error",
            task_state="failed",
            retry_count=0,
            max_retries=max_retries,
            queue_pending=pending,
            queue_running=running,
            queue_done=done,
            queue_failed=failed,
            queue_cancelled=cancelled,
            queue_skipped=skipped,
            last_event_type="pipeline_failed",
            last_event_message="interactive task raised an exception",
            last_task_finished_at=now_str(),
            error=str(exc)[:200],
            status_path=status_file,
        )
        raise

    duration = monotonic_duration(started)
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
    queue_upsert_execution_task(
        queue_file,
        thread_id,
        user_input,
        status,
        phase=result["phase"],
        retry_count=result["retry_count"],
        duration_s=duration,
        **({"error": "tests_failed"} if result.get("failed") else {}),
    )
    finished_at = now_str()
    pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
    update_status(
        worker_state="idle",
        current_task_id=None,
        current_task_description=None,
        last_task_id=thread_id,
        last_task_description=user_input,
        phase=result["phase"],
        task_state=status,
        retry_count=result["retry_count"],
        max_retries=max_retries,
        queue_pending=pending,
        queue_running=running,
        queue_done=done,
        queue_failed=failed,
        queue_cancelled=cancelled,
        queue_skipped=skipped,
        last_event_type="pipeline_failed" if result.get("failed") else "pipeline_done",
        last_event_message="interactive task failed" if result.get("failed") else "interactive task completed",
        last_task_finished_at=finished_at,
        error="tests_failed" if result.get("failed") else None,
        status_path=status_file,
    )
    save_memory_if_present_fn(user_input, report)
    print(f"[HARNESS] Task ID: {thread_id}\n")
