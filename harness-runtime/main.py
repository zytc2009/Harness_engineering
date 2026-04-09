"""
Harness Runtime — Multi-Agent CLI Entry Point
==============================================
Runs a simple architect → implementer → tester pipeline.
Each phase makes exactly one LLM call; no tool loops.

Usage:
  python main.py                   # New task
  python main.py --list            # List saved tasks
  python main.py --resume <id>     # Restart a saved task
  python main.py --phase tester    # Start from a specific phase
"""

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
from orchestrator import SANDBOX, run_pipeline, _read_sandbox

_TASKS_FILE = Path(__file__).parent / "harness_tasks.json"


# ── Task registry ──────────────────────────────────────────────────

def _load_tasks() -> list[dict]:
    if not _TASKS_FILE.exists():
        return []
    try:
        return json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return []


def _save_tasks(tasks: list[dict]) -> None:
    _TASKS_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def _upsert_task(thread_id: str, description: str, status: str, **extra) -> None:
    """Create or update a task record.

    extra kwargs (all optional):
        phase (str)       — last pipeline phase reached
        retry_count (int) — number of implementer retries used
        duration_s (float)— total wall-clock seconds for the run
        error (str)       — short error description on failure
    """
    tasks = _load_tasks()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for t in tasks:
        if t["id"] == thread_id:
            t["status"] = status
            t["updated"] = now
            t.update(extra)
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
    return [t for t in _load_tasks() if t["status"] in ("running", "failed")]


# ── Display helpers ────────────────────────────────────────────────

def print_banner(thread_id: str) -> None:
    print("=" * 55)
    print("  Harness Runtime — One-Shot Pipeline")
    for phase in ("architect", "implementer", "tester"):
        provider = config._resolve_provider(phase)
        model = config._resolve_model(phase)
        print(f"  {phase.capitalize():<12}: {provider} / {model}")
    print(f"  Sandbox      : {SANDBOX}")
    print(f"  Task ID      : {thread_id}")
    print("=" * 55)


def list_tasks() -> None:
    tasks = _load_tasks()
    if not tasks:
        print("No saved tasks.")
        return
    print(f"\n{'ID':<36}  {'Status':<10}  {'Phase':<12}  {'Retries':<7}  {'Duration':>8}  {'Updated':<19}  Description")
    print("─" * 120)
    for t in reversed(tasks):
        phase = t.get("phase", "—")
        retries = str(t.get("retry_count", "—"))
        dur = t.get("duration_s")
        dur_str = f"{dur}s" if dur is not None else "—"
        err = f"  ⚠ {t['error']}" if t.get("error") else ""
        print(
            f"{t['id']}  {t['status']:<10}  {phase:<12}  {retries:<7}  {dur_str:>8}  "
            f"{t['updated']:<19}  {t['description']}{err}"
        )
    print()


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Harness Runtime — One-Shot Pipeline")
    parser.add_argument("--resume", metavar="ID", help="Restart a saved task")
    parser.add_argument("--list", action="store_true", help="List all saved tasks")
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

    config.validate()

    # ── Choose task: resume or new ────────────────────────────────
    thread_id: str
    user_input: str
    start_phase: str = args.phase

    if args.resume:
        thread_id = args.resume
        tasks = _load_tasks()
        match = next((t for t in tasks if t["id"] == thread_id), None)
        if not match:
            print(f"[ERROR] Thread '{thread_id}' not found. Use --list to see saved tasks.")
            sys.exit(1)
        user_input = match["description"]
        print(f"\n[HARNESS] Resuming task: {user_input}")
        # Resume from implementer so we skip the architect/confirm step
        start_phase = "implementer"
    else:
        # Offer to resume incomplete tasks
        incomplete = _incomplete_tasks()
        if incomplete:
            print(f"\n[HARNESS] Found {len(incomplete)} incomplete task(s):")
            for i, t in enumerate(incomplete, 1):
                print(f"  [{i}] {t['id'][:8]}...  {t['updated']}  {t['description']}")
            print("  [N] Start a new task")
            choice = input("\nResume which? (1/2/.../N): ").strip().upper()
            if choice.isdigit() and 1 <= int(choice) <= len(incomplete):
                picked = incomplete[int(choice) - 1]
                thread_id = picked["id"]
                user_input = picked["description"]
                start_phase = "implementer"
                print(f"\n[HARNESS] Resuming: {user_input}")
            else:
                thread_id = str(uuid.uuid4())
                user_input = ""
        else:
            thread_id = str(uuid.uuid4())
            user_input = ""

        if not user_input:
            existing = load_memories()
            if existing:
                print(f"[HARNESS] Found {len(existing)} memory record(s).")
                print(f"          Last: {existing[-1]['date']} — {existing[-1]['summary'][:60]}...")
            else:
                print("[HARNESS] No long-term memory found. Starting fresh.")
            print("\nDescribe your task:")
            user_input = input("Task: ").strip()
            if not user_input:
                print("No task provided. Exiting.")
                return

    print_banner(thread_id)
    _upsert_task(thread_id, user_input, "running")

    max_retries = int(config.get_setting("MAX_RETRIES", "3"))
    t_start = time.monotonic()

    print("\n[HARNESS] Starting pipeline...\n")
    try:
        result = run_pipeline(task=user_input, start_phase=start_phase, max_retries=max_retries)
    except KeyboardInterrupt:
        duration = round(time.monotonic() - t_start, 1)
        print("\n\n[HARNESS] Interrupted.")
        _upsert_task(thread_id, user_input, "failed",
                     phase="interrupted", duration_s=duration,
                     error="KeyboardInterrupt")
        print(f"[HARNESS] Resume with: python main.py --resume {thread_id}\n")
        return
    except Exception as e:
        duration = round(time.monotonic() - t_start, 1)
        print(f"\n[HARNESS] Error: {e}")
        _upsert_task(thread_id, user_input, "failed",
                     duration_s=duration, error=str(e)[:200])
        raise

    duration = round(time.monotonic() - t_start, 1)

    # ── Output summary ────────────────────────────────────────────
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

    sandbox_files = _read_sandbox()
    if sandbox_files:
        print(f"\nFiles in sandbox ({len(sandbox_files)}):")
        for name in sorted(sandbox_files):
            print(f"  {name}")
    print(f"\nSandbox path: {SANDBOX}")
    print("=" * 55)
    print(f"  Phase     : {result['phase']}")
    print(f"  Retries   : {result['retry_count']}/{max_retries}")
    print(f"  Duration  : {duration}s")
    print("=" * 55)

    status = "done" if result["phase"] in ("done", "cancelled") else "running"
    _upsert_task(
        thread_id, user_input, status,
        phase=result["phase"],
        retry_count=result["retry_count"],
        duration_s=duration,
        **({"error": "tests_failed"} if result.get("failed") else {}),
    )

    # Save memory from tester report
    if report:
        print("\n[HARNESS] Extracting long-term memory...")
        from langchain_core.messages import HumanMessage, AIMessage
        msgs = [HumanMessage(content=user_input), AIMessage(content=report)]
        summary = extract_and_save_memory(msgs, user_input)
        print(f"[HARNESS] Memory saved: {summary}\n")

    print(f"[HARNESS] Task ID: {thread_id}\n")


if __name__ == "__main__":
    main()
