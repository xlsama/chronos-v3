"""Tests for the gather_context node — parallel sub agent execution."""

from unittest.mock import AsyncMock, patch

import pytest


async def test_gather_context_returns_history_summary():
    """gather_context node calls run_history_agent and returns summary."""
    with (
        patch("src.agent.nodes.gather_context.run_history_agent") as mock_history,
        patch("src.agent.nodes.gather_context.run_kb_agent") as mock_kb,
        patch("src.agent.nodes.gather_context.get_redis"),
    ):
        mock_history.return_value = "找到相似事件：磁盘满"
        mock_kb.return_value = "KB summary"

        from src.agent.nodes.gather_context import gather_context_node

        state = {
            "title": "Disk full",
            "description": "磁盘使用率 95%",
            "project_id": "test-pid",
            "_event_channel": "",
        }

        result = await gather_context_node(state)

    assert result["incident_history_summary"] == "找到相似事件：磁盘满"
    assert result["kb_summary"] == "KB summary"
    mock_history.assert_called_once()
    mock_kb.assert_called_once()


async def test_gather_context_handles_agent_failure():
    """gather_context node returns None when history agent fails."""
    with (
        patch("src.agent.nodes.gather_context.run_history_agent") as mock_history,
        patch("src.agent.nodes.gather_context.run_kb_agent") as mock_kb,
        patch("src.agent.nodes.gather_context.get_redis"),
    ):
        mock_history.side_effect = Exception("LLM timeout")
        mock_kb.return_value = "KB summary"

        from src.agent.nodes.gather_context import gather_context_node

        state = {
            "title": "Disk full",
            "description": "磁盘使用率 95%",
            "project_id": "test-pid",
            "_event_channel": "",
        }

        result = await gather_context_node(state)

    assert result["incident_history_summary"] is None
    assert result["kb_summary"] == "KB summary"


async def test_gather_context_skips_kb_without_project_id():
    """gather_context node skips KB agent when no project_id."""
    with (
        patch("src.agent.nodes.gather_context.run_history_agent") as mock_history,
        patch("src.agent.nodes.gather_context.run_kb_agent") as mock_kb,
        patch("src.agent.nodes.gather_context.get_redis"),
    ):
        mock_history.return_value = "历史事件摘要"

        from src.agent.nodes.gather_context import gather_context_node

        state = {
            "title": "Disk full",
            "description": "磁盘使用率 95%",
            "project_id": "",
            "_event_channel": "",
        }

        result = await gather_context_node(state)

    assert result["incident_history_summary"] == "历史事件摘要"
    assert result["kb_summary"] is None
    mock_kb.assert_not_called()


async def test_gather_context_with_event_channel():
    """gather_context node publishes events when channel is set."""
    mock_redis = AsyncMock()

    with (
        patch("src.agent.nodes.gather_context.run_history_agent") as mock_history,
        patch("src.agent.nodes.gather_context.run_kb_agent") as mock_kb,
        patch("src.agent.nodes.gather_context.get_redis", return_value=mock_redis),
    ):
        mock_history.return_value = "历史事件摘要"
        mock_kb.return_value = "KB摘要"

        from src.agent.nodes.gather_context import gather_context_node

        state = {
            "title": "Disk full",
            "description": "磁盘使用率 95%",
            "project_id": "test-pid",
            "_event_channel": "incident:test-123",
        }

        result = await gather_context_node(state)

    assert result["incident_history_summary"] == "历史事件摘要"
    assert result["kb_summary"] == "KB摘要"


async def test_gather_context_handles_kb_failure():
    """gather_context node returns None for KB when KB agent fails."""
    with (
        patch("src.agent.nodes.gather_context.run_history_agent") as mock_history,
        patch("src.agent.nodes.gather_context.run_kb_agent") as mock_kb,
        patch("src.agent.nodes.gather_context.get_redis"),
    ):
        mock_history.return_value = "History summary"
        mock_kb.side_effect = RuntimeError("KB agent error")

        from src.agent.nodes.gather_context import gather_context_node

        state = {
            "title": "Test",
            "description": "desc",
            "project_id": "test-pid",
            "_event_channel": "",
        }

        result = await gather_context_node(state)

    assert result["incident_history_summary"] == "History summary"
    assert result["kb_summary"] is None
