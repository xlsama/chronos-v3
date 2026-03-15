"""Tests for the gather_context node."""

from unittest.mock import AsyncMock, patch

import pytest


async def test_gather_context_returns_history_summary():
    """gather_context node calls run_history_agent and returns summary."""
    with patch("src.agent.nodes.gather_context.run_history_agent") as mock_history:
        mock_history.return_value = "找到相似事件：磁盘满"
        # Mock get_redis to avoid real Redis connection
        with patch("src.agent.nodes.gather_context.get_redis"):
            from src.agent.nodes.gather_context import gather_context_node

            state = {
                "title": "Disk full",
                "description": "磁盘使用率 95%",
                "project_id": "",
                "_event_channel": "",
            }

            result = await gather_context_node(state)

    assert result["incident_history_summary"] == "找到相似事件：磁盘满"
    mock_history.assert_called_once()


async def test_gather_context_handles_agent_failure():
    """gather_context node returns None when history agent fails."""
    with patch("src.agent.nodes.gather_context.run_history_agent") as mock_history:
        mock_history.side_effect = Exception("LLM timeout")
        with patch("src.agent.nodes.gather_context.get_redis"):
            from src.agent.nodes.gather_context import gather_context_node

            state = {
                "title": "Disk full",
                "description": "磁盘使用率 95%",
                "project_id": "",
                "_event_channel": "",
            }

            result = await gather_context_node(state)

    assert result["incident_history_summary"] is None


async def test_gather_context_with_event_channel():
    """gather_context node publishes events when channel is set."""
    mock_redis = AsyncMock()

    with (
        patch("src.agent.nodes.gather_context.run_history_agent") as mock_history,
        patch("src.agent.nodes.gather_context.get_redis", return_value=mock_redis),
    ):
        mock_history.return_value = "历史事件摘要"

        from src.agent.nodes.gather_context import gather_context_node

        state = {
            "title": "Disk full",
            "description": "磁盘使用率 95%",
            "project_id": "",
            "_event_channel": "incident:test-123",
        }

        result = await gather_context_node(state)

    assert result["incident_history_summary"] == "历史事件摘要"
    # The callback was constructed with a real channel, so run_history_agent was called with it
    call_kwargs = mock_history.call_args
    assert call_kwargs.kwargs["event_callback"] is not None
