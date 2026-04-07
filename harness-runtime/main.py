"""
Harness Runtime — Multi-Agent CLI Entry Point
==============================================
Reads task from user, runs the architect -> implementer -> tester loop,
saves session memory.

Usage:
  python main.py                  # Multi-agent mode (default)
  python main.py --single         # Single-agent mode (no phase routing)
  python main.py --phase tester   # Start from a specific phase
"""

import argparse
import sys

from langchain_core.messages import HumanMessage

import config
from memory import extract_and_save_memory, load_memories
from orchestrator import OrchestratorState, INITIAL_STATE, build_orchestrator


def print_banner():
    provider = config.get_setting("PROVIDER", "anthropic")
    main_model = config.get_setting("MAIN_MODEL", "claude-sonnet-4-20250514")
    memory_model = config.get_setting("MEMORY_MODEL", main_model)
    max_steps = config.get_setting("MAX_STEPS", "15")
    max_retries = config.get_setting("MAX_RETRIES", "3")

    print("=" * 55)
    print("  Harness Runtime — Multi-Agent Orchestrator")
    print(f"  Provider     : {provider}")
    print(f"  Main Model   : {main_model}")
    print(f"  Memory Model : {memory_model}")
    print(f"  Max Steps    : {max_steps}")
    print(f"  Max Retries  : {max_retries}")
    print("=" * 55)


def main():
    parser = argparse.ArgumentParser(description="Harness Runtime — Multi-Agent Dev Loop")
    parser.add_argument("--single", action="store_true", help="Single-agent mode (no phase routing)")
    parser.add_argument("--phase", default="architect", choices=["architect", "implementer", "tester"],
                        help="Starting phase (default: architect)")
    args = parser.parse_args()

    config.validate()
    print_banner()

    existing = load_memories()
    if existing:
        print(f"\n[HARNESS] Found {len(existing)} memory record(s).")
        print(f"          Last: {existing[-1]['date']} — {existing[-1]['summary'][:60]}...")
    else:
        print("\n[HARNESS] No long-term memory found. Starting fresh.")

    print("\nDescribe your task:")
    print("  Multi-agent mode: architect -> implementer -> tester (auto-loop)")
    if args.single:
        print("  [SINGLE-AGENT MODE] — no phase routing")
    print()

    user_input = input("Task: ").strip()
    if not user_input:
        print("No task provided. Exiting.")
        return

    init_state: OrchestratorState = {
        **INITIAL_STATE,
        "messages": [HumanMessage(content=user_input)],
        "phase": args.phase if not args.single else "implementer",
    }

    if args.single:
        init_state["max_retries"] = 0

    print("\n[HARNESS] Starting orchestrator...\n")
    orchestrator = build_orchestrator()
    final_state = orchestrator.invoke(init_state)

    final_messages = final_state["messages"]
    final_response = next(
        (m for m in reversed(final_messages)
         if hasattr(m, "content") and isinstance(m.content, str) and m.content.strip()),
        None,
    )

    print("\n" + "=" * 55)
    print("  FINAL RESPONSE")
    print("=" * 55)
    print(final_response.content if final_response else "(Task completed — see tool outputs above)")
    print("=" * 55)
    print(f"  Phase     : {final_state['phase']}")
    print(f"  Steps used: {final_state['step_count']}/{final_state['max_steps']}")
    print(f"  Retries   : {final_state['retry_count']}/{final_state['max_retries']}")
    print("=" * 55)

    print("\n[HARNESS] Extracting long-term memory...")
    summary = extract_and_save_memory(final_state["messages"], user_input)
    print(f"[HARNESS] Memory saved: {summary}\n")


if __name__ == "__main__":
    main()
