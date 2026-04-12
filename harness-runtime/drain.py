"""Queue drain worker logic."""

from __future__ import annotations

from pathlib import Path

import execution
from orchestrator import SANDBOX, run_pipeline
from status import update_status
from task_queue import load_queue, mark_stale_running_as_failed, next_pending, update_task as queue_update_task

from runtime_support import (
    last_task_snapshot,
    monotonic_duration,
    now_str,
    print_banner,
    queue_snapshot,
    queue_upsert_execution_task,
    save_memory_if_present,
    status_callback_for_task,
    task_sandbox_dir,
    write_idle_status,
)


def run_drain(max_retries: int, queue_file: Path, status_file: Path, sandbox_root: Path = SANDBOX) -> None:
    run_drain_with_hooks(max_retries, queue_file, status_file, sandbox_root=sandbox_root)


def run_drain_with_hooks(
    max_retries: int,
    queue_file: Path,
    status_file: Path,
    *,
    sandbox_root: Path = SANDBOX,
    print_banner_fn=print_banner,
    run_pipeline_fn=run_pipeline,
    save_memory_if_present_fn=save_memory_if_present,
) -> None:
    repaired = mark_stale_running_as_failed(queue_file)
    if repaired:
        print(f"[HARNESS] Recovered {repaired} interrupted running task(s).")

    while True:
        task = next_pending(queue_file)
        if task is None:
            write_idle_status(queue_file, status_file)
            print("\n[HARNESS] Queue empty. Drain finished.")
            return

        thread_id = task["id"]
        user_input = task["description"]
        task_max_retries = int(task.get("max_retries") or max_retries)
        task_metadata = {"constraints": task.get("constraints") or {}}
        sandbox_dir = task_sandbox_dir(thread_id, sandbox_root)
        execution.validate_runtime(task_metadata=task_metadata)
        print_banner_fn(thread_id, sandbox_dir, task_metadata=task_metadata)

        queue_update_task(
            thread_id,
            queue_path=queue_file,
            status="running",
            phase="architect",
            started_at=task.get("started_at") or now_str(),
            error=None,
            max_retries=task_max_retries,
        )
        queue_upsert_execution_task(
            queue_file,
            thread_id,
            user_input,
            "running",
            phase="architect",
            retry_count=0,
            source_doc=task.get("source_doc"),
            source_type=task.get("source_type"),
        )
        callback = status_callback_for_task(queue_file, status_file, thread_id, user_input, task_max_retries)
        callback({
            "type": "phase_started",
            "phase": "architect",
            "retry_count": 0,
            "error": None,
            "message": "architect started",
        })

        import time
        started = time.monotonic()
        try:
            result = run_pipeline_fn(
                task=user_input,
                start_phase="architect",
                max_retries=task_max_retries,
                sandbox_dir=sandbox_dir,
                on_status=callback,
                task_metadata=task_metadata,
            )
        except KeyboardInterrupt:
            duration = monotonic_duration(started)
            queue_update_task(
                thread_id,
                queue_path=queue_file,
                status="failed",
                phase="interrupted",
                error="interrupted",
                duration_s=duration,
                finished_at=now_str(),
            )
            queue_upsert_execution_task(
                queue_file,
                thread_id,
                user_input,
                "failed",
                phase="interrupted",
                duration_s=duration,
                error="interrupted",
                source_doc=task.get("source_doc"),
                source_type=task.get("source_type"),
            )
            pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
            update_status(
                worker_state="stopped",
                current_task_id=thread_id,
                current_task_description=user_input,
                last_task_id=task.get("id"),
                last_task_description=user_input,
                phase="interrupted",
                task_state="failed",
                retry_count=0,
                max_retries=task_max_retries,
                queue_pending=pending,
                queue_running=running,
                queue_done=done,
                queue_failed=failed,
                queue_cancelled=cancelled,
                queue_skipped=skipped,
                last_event_type="pipeline_interrupted",
                last_event_message="worker interrupted during task execution",
                last_task_finished_at=now_str(),
                error="interrupted",
                status_path=status_file,
            )
            print("\n[HARNESS] Interrupted. Remaining pending tasks were left untouched.")
            return
        except Exception as exc:
            duration = monotonic_duration(started)
            finished_at = now_str()
            queue_update_task(
                thread_id,
                queue_path=queue_file,
                status="failed",
                phase="error",
                error=str(exc)[:200],
                duration_s=duration,
                finished_at=finished_at,
            )
            queue_upsert_execution_task(
                queue_file,
                thread_id,
                user_input,
                "failed",
                phase="error",
                duration_s=duration,
                error=str(exc)[:200],
                source_doc=task.get("source_doc"),
                source_type=task.get("source_type"),
            )
            pending, running, done, failed_count, cancelled, skipped = queue_snapshot(queue_file)
            update_status(
                worker_state="running",
                current_task_id=thread_id,
                current_task_description=user_input,
                last_task_id=thread_id,
                last_task_description=user_input,
                phase="error",
                task_state="failed",
                retry_count=0,
                max_retries=task_max_retries,
                queue_pending=pending,
                queue_running=running,
                queue_done=done,
                queue_failed=failed_count,
                queue_cancelled=cancelled,
                queue_skipped=skipped,
                last_event_type="pipeline_failed",
                last_event_message="task raised an exception",
                last_task_finished_at=finished_at,
                error=str(exc)[:200],
                status_path=status_file,
            )
            print(f"\n[HARNESS] Task failed: {exc}")
            print("[HARNESS] Moving to next task...")
            continue

        duration = monotonic_duration(started)
        failed = bool(result.get("failed"))
        final_status = "failed" if failed else "done"
        final_error = "tests_failed" if failed else None
        finished_at = now_str()

        queue_update_task(
            thread_id,
            queue_path=queue_file,
            status=final_status,
            phase=result["phase"],
            retry_count=result["retry_count"],
            duration_s=duration,
            finished_at=finished_at,
            error=final_error,
        )
        queue_upsert_execution_task(
            queue_file,
            thread_id,
            user_input,
            final_status,
            phase=result["phase"],
            retry_count=result["retry_count"],
            duration_s=duration,
            source_doc=task.get("source_doc"),
            source_type=task.get("source_type"),
            **({"error": final_error} if final_error else {}),
        )
        pending, running, done, failed_count, cancelled, skipped = queue_snapshot(queue_file)
        update_status(
            worker_state="running",
            current_task_id=thread_id,
            current_task_description=user_input,
            last_task_id=thread_id,
            last_task_description=user_input,
            phase=result["phase"],
            task_state=final_status,
            retry_count=result["retry_count"],
            max_retries=task_max_retries,
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
            status_path=status_file,
        )

        save_memory_if_present_fn(user_input, result.get("tester_report", ""))
        print(f"[HARNESS] Task {final_status}: {thread_id}")
        if failed:
            print("[HARNESS] Moving to next task...")
