"""Shared helpers for harness-runtime CLI flows."""

from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path

import execution
from memory import extract_and_save_memory
from orchestrator import SANDBOX, _read_sandbox
from status import read_status, update_status
from task_queue import load_queue, queue_counts, upsert_task as queue_upsert_task


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def task_sandbox_dir(task_id: str, sandbox_root: Path = SANDBOX) -> Path:
    return sandbox_root / task_id


def task_log_prefix(task_id: str | None = None, phase: str | None = None) -> str:
    parts = ["[TASK]"]
    if task_id:
        parts[0] = f"[TASK {task_id[:8]}]"
    if phase:
        parts.append(f"[{phase}]")
    return "".join(parts)


def print_task_log(message: str, task_id: str | None = None, phase: str | None = None) -> None:
    print(f"{task_log_prefix(task_id, phase)} {message}")


def print_cli_log(message: str) -> None:
    print(f"[CLI] {message}")


def queue_snapshot(queue_file: Path) -> tuple[int, int, int, int, int, int]:
    return queue_counts(queue_file)


def last_task_snapshot(status_file: Path) -> tuple[str | None, str | None, str | None]:
    current = read_status(status_file) or {}
    return (
        current.get("last_task_id"),
        current.get("last_task_description"),
        current.get("last_task_finished_at"),
    )


def write_idle_status(queue_file: Path, status_file: Path) -> None:
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
        last_event_type="worker_idle",
        last_event_message="queue empty",
        last_task_finished_at=last_task_finished_at,
        status_path=status_file,
    )


def queue_upsert_execution_task(
    queue_file: Path,
    thread_id: str,
    description: str,
    status: str,
    **extra,
) -> None:
    existing = next((task for task in load_queue(queue_file) if task.get("id") == thread_id), None)
    now = now_str()
    record = {
        "id": thread_id,
        "description": description[:100],
        "status": status,
        "phase": None,
        "retry_count": 0,
        "max_retries": 3,
        "error": None,
        "created": now,
        "updated": now,
        "started_at": None,
        "finished_at": None,
        "duration_s": None,
        "source_doc": None,
        "source_type": None,
        "constraints": None,
    }
    if existing is not None:
        record.update(existing)
    record.update(extra)
    record["id"] = thread_id
    record["description"] = description[:100]
    record["status"] = status
    queue_upsert_task(record, queue_file)


def print_banner(thread_id: str, sandbox_dir: Path | None = None, task_metadata: dict | None = None) -> None:
    print("=" * 55)
    print(f"  Harness Runtime - Pipeline [{thread_id[:8]}]")
    for phase in ("architect", "implementer", "tester"):
        descriptor = execution.describe_phase_execution(phase, task_metadata=task_metadata)
        print(f"  {phase.capitalize():<12}: {descriptor}")
    if sandbox_dir is None:
        sandbox_dir = task_sandbox_dir(thread_id)
    print(f"  Sandbox      : {sandbox_dir}")
    print(f"  Task ID      : {thread_id}")
    print("=" * 55)


def confirm(prompt: str) -> bool:
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("yes", "y"):
            return True
        if answer in ("no", "n"):
            return False
        print("  Please type 'yes' or 'no'.")


def print_design_preview(sandbox_dir: Path) -> None:
    design = _read_sandbox(sandbox_dir).get("design.md", "")
    if not design:
        return
    lines = design.strip().splitlines()
    preview = "\n  ".join(lines[:20])
    print(f"\n{task_log_prefix(phase='architect')} Architect's plan:\n  {preview}")
    if len(lines) > 20:
        print(f"  ... ({len(lines) - 20} more lines - see design.md in sandbox)")
    print("\n" + "=" * 55)


def save_memory_if_present(user_input: str, tester_report: str) -> None:
    if not tester_report:
        return
    print_cli_log("Extracting long-term memory...")
    from langchain_core.messages import AIMessage, HumanMessage

    messages = [HumanMessage(content=user_input), AIMessage(content=tester_report)]
    summary = extract_and_save_memory(messages, user_input)
    print_cli_log(f"Memory saved: {summary}")
    print()


def _copy_sandbox_files(sandbox_dir: Path, dest_dir: Path) -> list[str]:
    """Copy all files from sandbox_dir to dest_dir. Returns list of copied filenames."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in sorted(sandbox_dir.iterdir()):
        if src.is_file():
            shutil.copy2(src, dest_dir / src.name)
            copied.append(src.name)
    return copied


def migrate_sandbox_output(sandbox_dir: Path, output_dir_raw: str) -> None:
    """Copy all sandbox files to output_dir (no git)."""
    output_dir = Path(output_dir_raw)
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    copied = _copy_sandbox_files(sandbox_dir, output_dir)
    if copied:
        print_task_log(f"Output -> {output_dir}")
        for name in copied:
            print(f"  {name}")
    else:
        print_task_log("migrate: sandbox is empty, nothing to copy")


def commit_workspace_output(sandbox_dir: Path, workspace_dir_raw: str, description: str) -> str:
    """Copy sandbox files to workspace_dir, git-init if needed, and commit.

    Returns the new HEAD SHA (empty string if sandbox was empty).
    """
    import git_ops

    workspace = Path(workspace_dir_raw)
    if not workspace.is_absolute():
        workspace = Path.cwd() / workspace
    git_ops.ensure_git_repo(workspace)
    copied = _copy_sandbox_files(sandbox_dir, workspace)
    if not copied:
        print_task_log("commit: sandbox is empty, nothing to commit")
        return ""
    short_desc = description[:72].strip() if description else "harness task"
    sha = git_ops.commit_subtask(workspace, copied, f"feat: {short_desc}")
    print_task_log(f"Committed -> {workspace} ({sha[:8]})")
    for name in copied:
        print(f"  {name}")
    return sha


def status_callback_for_task(queue_file: Path, status_file: Path, thread_id: str, description: str, max_retries: int):
    _phase_start: dict[str, float] = {}

    def callback(event: dict) -> None:
        pending, running, done, failed, cancelled, skipped = queue_snapshot(queue_file)
        last_task_id, last_task_description, last_task_finished_at = last_task_snapshot(status_file)
        event_type = event.get("type")
        phase = event.get("phase")
        retry_count = event.get("retry_count", 0)
        error = event.get("error")
        message = event.get("message")

        tag = f"[{description[:20]}]" if description else "[task]"
        now = time.monotonic()
        if event_type == "phase_started" and phase:
            _phase_start[phase] = now
            print_task_log(f"{tag} started", thread_id, phase)
        elif event_type == "phase_finished" and phase:
            elapsed = now - _phase_start.get(phase, now)
            print_task_log(f"{tag} ✓ ({elapsed:.1f}s)", thread_id, phase)
        elif event_type == "retrying":
            print_task_log(f"{tag} ↻ retry {retry_count}/{max_retries}", thread_id, phase)

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
            last_task_id=last_task_id,
            last_task_description=last_task_description,
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
            last_task_finished_at=last_task_finished_at,
            error=error,
            status_path=status_file,
        )

    return callback


def monotonic_duration(started: float) -> float:
    return round(time.monotonic() - started, 1)
