"""Tests for the history sub agent and search_incident_history tool."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage


# ── search_incident_history tool ──


async def test_search_incident_history_tool():
    """Tool returns formatted string from service results."""
    mock_results = [
        {
            "title": "Disk Full Alert",
            "summary_md": "Disk was 95% full, cleaned logs.",
            "distance": 0.15,
            "relevance_score": 0.92,
        }
    ]

    mock_session = AsyncMock()
    mock_service = AsyncMock()
    mock_service.search.return_value = mock_results

    with (
        patch("src.tools.history_tools.get_session_factory") as mock_factory,
        patch("src.tools.history_tools.IncidentHistoryService", return_value=mock_service),
    ):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = lambda: mock_ctx

        from src.tools.history_tools import search_incident_history

        result = await search_incident_history(query="disk full", project_id="")

    assert "历史事件参考" in result
    assert "Disk Full Alert" in result
    assert "0.92" in result  # relevance_score from reranker


async def test_search_incident_history_no_results():
    """Tool returns no-match message when no results found."""
    mock_session = AsyncMock()
    mock_service = AsyncMock()
    mock_service.search.return_value = []

    with (
        patch("src.tools.history_tools.get_session_factory") as mock_factory,
        patch("src.tools.history_tools.IncidentHistoryService", return_value=mock_service),
    ):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = lambda: mock_ctx

        from src.tools.history_tools import search_incident_history

        result = await search_incident_history(query="unknown issue")

    assert "暂无相似历史事件" in result


# ── History Sub Agent ──


class FakeStreamingLLM:
    """Fake LLM that returns pre-defined responses, simulating streaming."""

    def __init__(self, responses: list[AIMessage]):
        self._responses = list(responses)
        self._call_index = 0

    def bind_tools(self, tools):
        self._tools = tools
        return self

    async def astream(self, messages, **kwargs):
        if self._call_index >= len(self._responses):
            yield AIMessage(content="Done")
            return
        response = self._responses[self._call_index]
        self._call_index += 1
        yield response


async def test_history_agent_calls_search_and_summarizes():
    """History agent calls search tool and returns summary."""
    events = []

    async def capture_callback(event_type: str, data: dict):
        events.append({"event_type": event_type, "data": data})

    # Response 1: call search tool
    # Response 2: summary after tool result
    fake_responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_incident_history_tool",
                    "args": {"query": "磁盘满"},
                    "id": "tc-1",
                }
            ],
        ),
        AIMessage(content="找到一个相似事件：磁盘满导致服务异常，清理日志后恢复。"),
    ]

    fake_llm = FakeStreamingLLM(fake_responses)

    with (
        patch("src.agent.sub_agents.history_agent.ChatOpenAI", return_value=fake_llm),
        patch("src.agent.sub_agents.history_agent.search_incident_history") as mock_search,
    ):
        mock_search.return_value = "## 历史事件参考\n\n### 磁盘满 (相似度: 0.85)\n清理日志后恢复。"

        from src.agent.sub_agents.history_agent import run_history_agent

        result = await run_history_agent(
            title="磁盘使用率过高",
            description="服务器 /dev/sda1 95% full",
            project_id="",
            event_callback=capture_callback,
        )

    assert "相似事件" in result
    # Should have emitted tool_call and tool_result events
    event_types = [e["event_type"] for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types


async def test_history_agent_no_results():
    """History agent returns no-match message when search yields nothing."""
    events = []

    async def capture_callback(event_type: str, data: dict):
        events.append({"event_type": event_type, "data": data})

    fake_responses = [
        AIMessage(content="暂无相似历史事件，没有找到可参考的历史记录。"),
    ]

    fake_llm = FakeStreamingLLM(fake_responses)

    with patch("src.agent.sub_agents.history_agent.ChatOpenAI", return_value=fake_llm):
        from src.agent.sub_agents.history_agent import run_history_agent

        result = await run_history_agent(
            title="Unknown error",
            description="Something weird happened",
            project_id="",
            event_callback=capture_callback,
        )

    assert "暂无相似历史事件" in result
    # Should have thinking events
    event_types = [e["event_type"] for e in events]
    assert "thinking" in event_types
