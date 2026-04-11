"""
Harness Runtime CLI Entry Point
===============================
Thin CLI layer for queue, drain, and interactive execution.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=Warning, module="requests")


def _configure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")

import config
from drain import run_drain_with_hooks
from interactive import choose_interactive_task, run_single_task_with_hooks
from memory import extract_and_save_memory
from orchestrator import SANDBOX, architect_phase, run_pipeline
from queue_cli import (
    handle_add as queue_handle_add,
    handle_add_file as queue_handle_add_file,
    handle_cancel as queue_handle_cancel,
    handle_skip as queue_handle_skip,
    list_tasks as queue_list_tasks,
    print_queue as queue_print_queue,
    print_queue_json as queue_print_queue_json,
    show_status as queue_show_status,
    show_status_json as queue_show_status_json,
)
from runtime_support import print_banner
from task_doc import TaskDocValidationError, validate_task_doc as runtime_validate_task_doc
from task_queue import load_queue

_QUEUE_FILE = Path(__file__).parent / "task_queue.json"
_STATUS_FILE = Path(__file__).parent / "status.json"


def _save_memory_if_present(user_input: str, tester_report: str) -> None:
    if not tester_report:
        return
    print("\n[HARNESS] Extracting long-term memory...")
    from langchain_core.messages import AIMessage, HumanMessage

    messages = [HumanMessage(content=user_input), AIMessage(content=tester_report)]
    summary = extract_and_save_memory(messages, user_input)
    print(f"[HARNESS] Memory saved: {summary}\n")


def list_tasks() -> None:
    queue_list_tasks(_QUEUE_FILE)


def handle_add(description: str, max_retries: int = 3) -> str:
    return queue_handle_add(description, max_retries, _QUEUE_FILE, _STATUS_FILE)


def handle_add_file(doc_path: str, max_retries: int = 3) -> str:
    return queue_handle_add_file(doc_path, max_retries, _QUEUE_FILE, _STATUS_FILE)


def handle_validate_task_doc(doc_path: str) -> None:
    resolved_path, sections, constraints = runtime_validate_task_doc(doc_path)
    print(f"[HARNESS] Task document is valid: {resolved_path}")
    print(f"  Required sections: {', '.join(name for name in sections if sections.get(name))}")
    print(f"  Constraints: {len(constraints)} parsed")


def handle_cancel(task_id: str) -> None:
    queue_handle_cancel(task_id, _QUEUE_FILE, _STATUS_FILE)


def handle_skip(task_id: str) -> None:
    queue_handle_skip(task_id, _QUEUE_FILE, _STATUS_FILE)


def show_status() -> None:
    queue_show_status(_STATUS_FILE)


def show_status_json() -> None:
    queue_show_status_json(_STATUS_FILE)


def _print_queue() -> None:
    queue_print_queue(_QUEUE_FILE)


def _print_queue_json() -> None:
    queue_print_queue_json(_QUEUE_FILE)


def run_drain(max_retries: int = 3) -> None:
    run_drain_with_hooks(
        max_retries,
        _QUEUE_FILE,
        _STATUS_FILE,
        sandbox_root=SANDBOX,
        print_banner_fn=print_banner,
        run_pipeline_fn=run_pipeline,
        save_memory_if_present_fn=_save_memory_if_present,
    )


def _choose_interactive_task() -> tuple[str, str, str]:
    return choose_interactive_task(_QUEUE_FILE)


def _run_single_task(thread_id: str, user_input: str, start_phase: str, max_retries: int) -> None:
    from runtime_support import confirm, print_design_preview

    run_single_task_with_hooks(
        thread_id,
        user_input,
        start_phase,
        max_retries,
        _QUEUE_FILE,
        _STATUS_FILE,
        sandbox_root=SANDBOX,
        print_banner_fn=print_banner,
        architect_phase_fn=architect_phase,
        run_pipeline_fn=run_pipeline,
        print_design_preview_fn=print_design_preview,
        confirm_fn=confirm,
        save_memory_if_present_fn=_save_memory_if_present,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Harness Runtime - Queue and Pipeline")
    parser.add_argument("--resume", metavar="ID", help="Restart a saved task")
    parser.add_argument("--list", action="store_true", help="List all saved tasks")
    parser.add_argument("--add", metavar="DESC", help="Add a task to the queue")
    parser.add_argument("--add-file", metavar="PATH", help="Add a ready task document to the queue")
    parser.add_argument("--validate-task-doc", metavar="PATH", help="Validate a task document without enqueueing")
    parser.add_argument("--cancel", metavar="ID", help="Cancel a pending queued task")
    parser.add_argument("--skip", metavar="ID", help="Skip a pending queued task")
    parser.add_argument("--queue", action="store_true", help="List queued tasks")
    parser.add_argument("--queue-json", action="store_true", help="List queued tasks as JSON")
    parser.add_argument("--status", action="store_true", help="Show current worker status")
    parser.add_argument("--status-json", action="store_true", help="Show current worker status as JSON")
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
    try:
        if args.add_file:
            max_retries = int(config.get_setting("MAX_RETRIES", "3"))
            handle_add_file(args.add_file, max_retries=max_retries)
            return
        if args.validate_task_doc:
            handle_validate_task_doc(args.validate_task_doc)
            return
    except TaskDocValidationError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    if args.cancel:
        handle_cancel(args.cancel)
        return
    if args.skip:
        handle_skip(args.skip)
        return
    if args.queue:
        _print_queue()
        return
    if args.queue_json:
        _print_queue_json()
        return
    if args.status:
        show_status()
        return
    if args.status_json:
        show_status_json()
        return
    if args.drain:
        max_retries = int(config.get_setting("MAX_RETRIES", "3"))
        run_drain(max_retries=max_retries)
        return

    config.validate()
    max_retries = int(config.get_setting("MAX_RETRIES", "3"))

    if args.resume:
        tasks = load_queue(_QUEUE_FILE)
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
    _configure_utf8_stdio()
    main()
