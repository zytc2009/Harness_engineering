"""Tests for orchestrator — multi-agent state machine transitions."""

from unittest.mock import MagicMock

import pytest
from orchestrator import (
    OrchestratorState,
    route_after_agent,
    route_after_guard,
    route_after_phase,
    route_phase_transition,
    INITIAL_STATE,
    build_orchestrator,
)


def _make_msg(content="", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    return msg


class TestInitialState:
    def test_starts_with_architect_phase(self):
        assert INITIAL_STATE["phase"] == "architect"

    def test_starts_with_zero_steps(self):
        assert INITIAL_STATE["step_count"] == 0

    def test_starts_with_zero_retries(self):
        assert INITIAL_STATE["retry_count"] == 0

    def test_starts_approved(self):
        assert INITIAL_STATE["approved"] is True


class TestRouteAfterAgent:
    def test_routes_to_guard_when_tool_calls(self):
        state = {
            "messages": [_make_msg(tool_calls=[{"name": "write_file", "args": {}}])],
            "step_count": 1,
            "max_steps": 15,
            "phase": "architect",
            "retry_count": 0,
            "approved": True,
        }
        assert route_after_agent(state) == "guard"

    def test_routes_to_phase_transition_when_no_tool_calls(self):
        state = {
            "messages": [_make_msg()],
            "step_count": 1,
            "max_steps": 15,
            "phase": "architect",
            "retry_count": 0,
            "approved": True,
        }
        assert route_after_agent(state) == "phase_transition"

    def test_routes_to_end_when_max_steps_reached(self):
        state = {
            "messages": [_make_msg()],
            "step_count": 15,
            "max_steps": 15,
            "phase": "architect",
            "retry_count": 0,
            "approved": True,
        }
        assert route_after_agent(state) == "__end__"


class TestRouteAfterGuard:
    def test_routes_to_tools_when_approved(self):
        assert route_after_guard({"approved": True}) == "tools"

    def test_routes_to_end_when_rejected(self):
        assert route_after_guard({"approved": False}) == "__end__"


class TestRouteAfterPhase:
    def test_done_goes_to_end(self):
        assert route_after_phase({"phase": "done"}) == "__end__"

    def test_non_done_goes_to_agent(self):
        assert route_after_phase({"phase": "implementer"}) == "agent"


class TestRoutePhaseTransition:
    def test_architect_goes_to_implementer(self):
        result = route_phase_transition({
            "phase": "architect", "retry_count": 0, "max_retries": 3, "messages": [],
        })
        assert result["phase"] == "implementer"

    def test_implementer_goes_to_tester(self):
        result = route_phase_transition({
            "phase": "implementer", "retry_count": 0, "max_retries": 3, "messages": [],
        })
        assert result["phase"] == "tester"

    def test_tester_pass_goes_to_done(self):
        result = route_phase_transition({
            "phase": "tester",
            "retry_count": 0,
            "max_retries": 3,
            "messages": [_make_msg("ALL TESTS PASSED")],
        })
        assert result["phase"] == "done"

    def test_tester_fail_retries_implementer(self):
        result = route_phase_transition({
            "phase": "tester",
            "retry_count": 0,
            "max_retries": 3,
            "messages": [_make_msg("TESTS FAILED: something broke")],
        })
        assert result["phase"] == "implementer"
        assert result["retry_count"] == 1

    def test_tester_fail_max_retries_goes_to_done(self):
        result = route_phase_transition({
            "phase": "tester",
            "retry_count": 3,
            "max_retries": 3,
            "messages": [_make_msg("TESTS FAILED: still broken")],
        })
        assert result["phase"] == "done"


class TestGraphBuild:
    def test_build_orchestrator_compiles(self):
        graph = build_orchestrator()
        assert graph is not None

    def test_has_expected_nodes(self):
        graph = build_orchestrator()
        node_names = set(graph.get_graph().nodes.keys())
        assert "agent" in node_names
        assert "guard" in node_names
        assert "tools" in node_names
        assert "phase_transition" in node_names
