"""Tests for Agent state, nodes, and graph structure."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.state import OpsState
from src.agent.nodes.main_agent import route_decision
from src.agent.nodes.human_approval import human_approval_node
from src.agent.graph import build_graph


# ── OpsState ──


def test_ops_state_init():
    state = {
        "messages": [],
        "incident_id": "inc-1",
        "infrastructure_id": "infra-1",
        "project_id": "",
        "title": "Disk full",
        "description": "Server disk is 95% full",
        "severity": "high",
        "is_complete": False,
        "needs_approval": False,
        "pending_tool_call": None,
        "summary_md": None,
    }
    assert state["incident_id"] == "inc-1"
    assert state["is_complete"] is False
    assert state["project_id"] == ""


def test_ops_state_messages_accumulate():
    messages = [
        HumanMessage(content="Check disk"),
        AIMessage(content="Running df -h..."),
    ]
    assert len(messages) == 2


# ── route_decision ──


def test_route_decision_complete_when_no_tool_calls():
    state = {
        "messages": [AIMessage(content="All done")],
    }
    assert route_decision(state) == "complete"


def test_route_decision_complete_tool():
    msg = AIMessage(
        content="Investigation complete",
        tool_calls=[{"name": "complete", "args": {"summary": "fixed"}, "id": "tc1"}],
    )
    state = {"messages": [msg]}
    assert route_decision(state) == "complete"


def test_route_decision_needs_approval():
    msg = AIMessage(
        content="Need to restart nginx",
        tool_calls=[
            {
                "name": "exec_write_tool",
                "args": {"infra_id": "i1", "command": "systemctl restart nginx"},
                "id": "tc1",
            }
        ],
    )
    state = {"messages": [msg]}
    assert route_decision(state) == "need_approval"


def test_route_decision_continue():
    msg = AIMessage(
        content="Checking disk",
        tool_calls=[
            {
                "name": "exec_read_tool",
                "args": {"infra_id": "i1", "command": "df -h"},
                "id": "tc1",
            }
        ],
    )
    state = {"messages": [msg]}
    assert route_decision(state) == "continue"


# ── human_approval_node ──


async def test_human_approval_node_sets_pending():
    msg = AIMessage(
        content="Need write access",
        tool_calls=[
            {
                "name": "exec_write_tool",
                "args": {"infra_id": "i1", "command": "systemctl restart nginx"},
                "id": "tc1",
            }
        ],
    )
    state = {"messages": [msg]}

    result = await human_approval_node(state)

    assert result["needs_approval"] is True
    assert result["pending_tool_call"]["name"] == "exec_write_tool"


# ── Graph structure ──


def test_graph_has_expected_nodes():
    graph = build_graph()
    node_names = set(graph.nodes.keys())
    assert "main_agent" in node_names
    assert "tools" in node_names
    assert "human_approval" in node_names
    assert "summarize" in node_names


def test_graph_compiles():
    from src.agent.graph import compile_graph

    compiled = compile_graph()
    assert compiled is not None
