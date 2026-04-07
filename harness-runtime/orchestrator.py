"""
Multi-Agent Orchestrator
========================
LangGraph state machine that implements the architect -> implementer -> tester
self-healing loop.

Graph topology:
  agent_node -> route_after_agent
    |-- has tool calls? -> guard_node -> route_after_guard
    |                        |-- approved -> tool_node -> agent_node (loop)
    |                        +-- rejected -> END
    |-- max steps? -> END
    +-- no tool calls -> phase_transition -> route_after_phase
                            |-- phase != done -> agent_node (next role)
                            +-- phase == done -> END
"""

from typing import Annotated

from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

import config
from guard import should_confirm, request_human_approval
from prompts import get_system_prompt
from tools import TOOLS


# ── State Definition ───────────────────────────────────────────────

class OrchestratorState(TypedDict):
    messages: Annotated[list, add_messages]
    phase: str          # "architect" | "implementer" | "tester" | "done"
    step_count: int
    max_steps: int
    max_retries: int
    retry_count: int
    approved: bool


INITIAL_STATE: OrchestratorState = {
    "messages": [],
    "phase": "architect",
    "step_count": 0,
    "max_steps": int(config.get_setting("MAX_STEPS", "15")),
    "max_retries": int(config.get_setting("MAX_RETRIES", "3")),
    "retry_count": 0,
    "approved": True,
}


# ── Nodes ──────────────────────────────────────────────────────────

def agent_node(state: OrchestratorState) -> dict:
    """Model inference node. Uses phase to select the correct role prompt."""
    phase = state["phase"]
    system_prompt = get_system_prompt(phase)
    system_msg = SystemMessage(content=system_prompt)
    messages = [system_msg] + state["messages"]

    step = state["step_count"] + 1
    max_s = state["max_steps"]
    print(f"\n[HARNESS] Step {step}/{max_s} | Phase: {phase} | Thinking...")

    llm = config.get_llm().bind_tools(TOOLS)
    response = llm.invoke(messages)

    return {
        "messages": [response],
        "step_count": step,
    }


def guard_node(state: OrchestratorState) -> dict:
    """Safety guard node. Checks tool calls for dangerous operations."""
    last = state["messages"][-1]
    approved = True

    if hasattr(last, "tool_calls") and last.tool_calls:
        for call in last.tool_calls:
            if should_confirm(call["name"], call["args"]):
                approved = request_human_approval(call["name"], call["args"])
                if not approved:
                    break

    return {"approved": approved}


tool_node = ToolNode(TOOLS)


def phase_transition_node(state: OrchestratorState) -> dict:
    """Transition between agent phases based on current phase and results."""
    result = route_phase_transition(state)
    phase = result["phase"]

    if phase == "done":
        print(f"\n[HARNESS] All phases complete. Retry count: {state['retry_count']}")
    else:
        prev = state["phase"]
        if phase == "implementer" and prev == "tester":
            print(f"\n[HARNESS] Tests failed. Retrying implementation "
                  f"(attempt {result.get('retry_count', state['retry_count'])}/{state['max_retries']})")
        else:
            print(f"\n[HARNESS] Phase transition: {prev} -> {phase}")

    return result


# ── Routing Functions ──────────────────────────────────────────────

def route_after_agent(state: OrchestratorState) -> str:
    """After agent thinks: check for tool calls, max steps, or phase transition."""
    if state["step_count"] >= state["max_steps"]:
        print(f"\n[HARNESS] Max steps ({state['max_steps']}) reached. Stopping.")
        return END

    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "guard"

    return "phase_transition"


def route_after_guard(state: OrchestratorState) -> str:
    """After guard: proceed to tools if approved, else stop."""
    return "tools" if state["approved"] else END


def route_after_phase(state: OrchestratorState) -> str:
    """After phase transition: continue to next agent or end."""
    return END if state["phase"] == "done" else "agent"


def route_phase_transition(state: OrchestratorState) -> dict:
    """Determine the next phase based on current phase and test results.

    Returns:
        Dict with updated phase (and optionally retry_count).
    """
    phase = state["phase"]

    if phase == "architect":
        return {"phase": "implementer"}

    if phase == "implementer":
        return {"phase": "tester"}

    if phase == "tester":
        last = state["messages"][-1]
        content = last.content if isinstance(last.content, str) else str(last.content)

        if "ALL TESTS PASSED" in content.upper():
            return {"phase": "done"}

        if state["retry_count"] < state["max_retries"]:
            return {"phase": "implementer", "retry_count": state["retry_count"] + 1}

        print(f"\n[HARNESS] Max retries ({state['max_retries']}) reached. Finishing with failures.")
        return {"phase": "done"}

    return {"phase": "done"}


# ── Graph Builder ──────────────────────────────────────────────────

def build_orchestrator():
    """Build and compile the multi-agent LangGraph."""
    graph = StateGraph(OrchestratorState)

    graph.add_node("agent", agent_node)
    graph.add_node("guard", guard_node)
    graph.add_node("tools", tool_node)
    graph.add_node("phase_transition", phase_transition_node)

    graph.set_entry_point("agent")

    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_conditional_edges("guard", route_after_guard)
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("phase_transition", route_after_phase)

    return graph.compile()
