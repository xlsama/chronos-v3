"""Tests for ask_human node and route_decision."""

from unittest.mock import MagicMock

from src.agent.nodes.main_agent import route_decision


class TestRouteDecisionAskHuman:
    def test_routes_to_ask_human(self):
        state = {
            "messages": [
                MagicMock(
                    tool_calls=[{"name": "ask_human", "args": {"question": "Which service?"}}]
                )
            ]
        }
        assert route_decision(state) == "ask_human"

    def test_routes_to_continue_for_normal_tools(self):
        state = {
            "messages": [
                MagicMock(
                    tool_calls=[{"name": "exec_read_tool", "args": {"command": "ls"}}]
                )
            ]
        }
        assert route_decision(state) == "continue"

    def test_routes_to_ask_human_when_no_tool_calls(self):
        msg = MagicMock(spec=[])  # no tool_calls attribute
        state = {"messages": [msg]}
        assert route_decision(state) == "ask_human"

    def test_routes_to_need_approval_for_exec_write(self):
        state = {
            "messages": [
                MagicMock(
                    tool_calls=[{"name": "exec_write_tool", "args": {}}]
                )
            ]
        }
        assert route_decision(state) == "need_approval"

    def test_routes_to_complete_for_complete_tool(self):
        state = {
            "messages": [
                MagicMock(
                    tool_calls=[{"name": "complete", "args": {"summary": "done"}}]
                )
            ]
        }
        assert route_decision(state) == "complete"
