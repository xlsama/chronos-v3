"""E2E test: full agent flow with mock LLM + mock SSH.

Tests the complete cycle:
  create event → gather_context → Agent start → tool calls → approval interrupt → resume → summary
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agent.graph import compile_graph
from src.connectors.ssh import SSHResult
from src.tools.exec_tools import _connector_registry, register_connector

INFRA_ID = "test-infra-001"


# ── FakeLLM ──


class FakeLLM:
    """Returns pre-defined AIMessages in sequence to drive the agent through all phases."""

    def __init__(self, responses: list[AIMessage]):
        self._responses = list(responses)
        self._call_index = 0

    async def ainvoke(self, messages, **kwargs):
        if self._call_index >= len(self._responses):
            # Fallback: no more tool calls, just complete
            return AIMessage(content="Done")
        response = self._responses[self._call_index]
        self._call_index += 1
        return response

    def bind_tools(self, tools):
        return self


def build_fake_responses() -> list[AIMessage]:
    """Build the sequence of AIMessages the FakeLLM will return.

    Call 1: exec_read_tool(df -h) → read-only, goes through tools → back to main_agent
    Call 2: exec_write_tool(systemctl restart nginx) → triggers human_approval interrupt
    Call 3: (after resume) complete(summary="...") → triggers summarize → END
    """
    return [
        # Call 1: read command
        AIMessage(
            content="Let me check disk usage",
            tool_calls=[
                {
                    "name": "exec_read_tool",
                    "args": {"infra_id": INFRA_ID, "command": "df -h"},
                    "id": "tc-read-1",
                }
            ],
        ),
        # Call 2: write command (triggers approval)
        AIMessage(
            content="Need to restart nginx",
            tool_calls=[
                {
                    "name": "exec_write_tool",
                    "args": {
                        "infra_id": INFRA_ID,
                        "command": "systemctl restart nginx",
                        "explanation": "重启 nginx 恢复服务",
                        "risk_level": "MEDIUM",
                        "risk_detail": "短暂服务中断",
                    },
                    "id": "tc-write-1",
                }
            ],
        ),
        # Call 3: after resume + tool execution, agent completes
        AIMessage(
            content="Investigation complete",
            tool_calls=[
                {
                    "name": "complete",
                    "args": {"summary": "Disk was full, restarted nginx to resolve."},
                    "id": "tc-complete-1",
                }
            ],
        ),
    ]


# ── Mock SSH connector ──


def make_mock_ssh() -> AsyncMock:
    connector = AsyncMock()

    async def fake_execute(command: str) -> SSHResult:
        if "df" in command:
            return SSHResult(
                exit_code=0,
                stdout="Filesystem  Size  Used Avail Use%\n/dev/sda1   50G   47G   3G  94%",
                stderr="",
            )
        if "systemctl" in command:
            return SSHResult(exit_code=0, stdout="", stderr="")
        return SSHResult(exit_code=0, stdout="ok", stderr="")

    connector.execute = AsyncMock(side_effect=fake_execute)
    return connector


# ── Tests ──


@pytest.fixture(autouse=True)
def cleanup_connector_registry():
    """Ensure ssh registry is clean before/after each test."""
    _connector_registry.clear()
    yield
    _connector_registry.clear()


async def test_full_agent_flow():
    """Full E2E: gather_context → agent runs → read tool → write tool (interrupt) → resume → complete → summarize."""
    checkpointer = MemorySaver()

    # Register mock SSH
    mock_ssh = make_mock_ssh()
    register_connector(INFRA_ID, mock_ssh)

    fake_llm = FakeLLM(build_fake_responses())
    mock_summarize_llm = AsyncMock()
    mock_summarize_llm.ainvoke.return_value = AIMessage(
        content="## 排查报告\n\n磁盘使用率 94%，已重启 nginx 恢复服务。"
    )

    with (
        patch("src.agent.nodes.main_agent.get_llm", return_value=fake_llm),
        patch("src.agent.nodes.summarize.ChatOpenAI", return_value=mock_summarize_llm),
        patch("src.agent.nodes.gather_context.run_history_agent", return_value="暂无相似历史事件"),
        patch("src.agent.nodes.gather_context.get_redis"),
    ):
        graph = compile_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "test-thread-1"}}

        initial_state = {
            "messages": [HumanMessage(content="事件: Disk full\n\n磁盘使用率过高")],
            "incident_id": "inc-001",
            "infrastructure_id": INFRA_ID,
            "project_id": "",
            "title": "Disk full",
            "description": "磁盘使用率过高",
            "severity": "high",
            "is_complete": False,
            "needs_approval": False,
            "pending_tool_call": None,
            "summary_md": None,
            "incident_history_summary": None,
            "_event_channel": "",
        }

        # Phase 1: Run until approval interrupt
        events = []
        async for chunk in graph.astream(initial_state, config):
            events.append(chunk)

        state = await graph.aget_state(config)
        # Should be interrupted before human_approval
        assert state.next == ("human_approval",), f"Expected interrupt at human_approval, got {state.next}"

        # Verify exec_read_tool was called (SSH execute for df -h)
        read_calls = [
            c for c in mock_ssh.execute.call_args_list if "df" in str(c)
        ]
        assert len(read_calls) == 1, "exec_read_tool should have called SSH once with df -h"

        # Phase 2: Resume (simulate approval granted)
        events2 = []
        async for chunk in graph.astream(None, config):
            events2.append(chunk)

        final = await graph.aget_state(config)
        assert final.next == (), f"Expected flow to be complete, got {final.next}"
        assert final.values["is_complete"] is True
        assert final.values["summary_md"] is not None
        assert "排查报告" in final.values["summary_md"]

        # Verify SSH was called for the write command too
        write_calls = [
            c for c in mock_ssh.execute.call_args_list if "systemctl" in str(c)
        ]
        assert len(write_calls) == 1, "exec_write_tool should have called SSH once with systemctl"

        # Verify message history has the expected tool calls
        messages = final.values["messages"]
        tool_names = [m.name for m in messages if hasattr(m, "name") and m.name]
        assert "exec_read_tool" in tool_names
        assert "exec_write_tool" in tool_names


async def test_agent_runner_with_events():
    """Test AgentRunner publishes events via EventPublisher."""
    import fakeredis.aioredis

    from src.agent.event_publisher import EventPublisher
    from src.services.agent_runner import AgentRunner

    checkpointer = MemorySaver()

    # Mock SSH
    mock_ssh = make_mock_ssh()
    register_connector(INFRA_ID, mock_ssh)

    # Only one response: exec_read then complete
    fake_responses = [
        AIMessage(
            content="Checking disk",
            tool_calls=[
                {
                    "name": "exec_read_tool",
                    "args": {"infra_id": INFRA_ID, "command": "df -h"},
                    "id": "tc-read-1",
                }
            ],
        ),
        AIMessage(
            content="All good",
            tool_calls=[
                {
                    "name": "complete",
                    "args": {"summary": "Disk OK"},
                    "id": "tc-complete-1",
                }
            ],
        ),
    ]
    fake_llm = FakeLLM(fake_responses)

    mock_summarize_llm = AsyncMock()
    mock_summarize_llm.ainvoke.return_value = AIMessage(content="## Summary\nDisk OK")

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    publisher = EventPublisher(redis=redis)

    # Collect published events
    published_events = []
    original_publish = publisher.publish

    async def capture_publish(channel, event_type, data):
        published_events.append({"channel": channel, "event_type": event_type, "data": data})
        await original_publish(channel, event_type, data)

    publisher.publish = capture_publish

    with (
        patch("src.agent.nodes.main_agent.get_llm", return_value=fake_llm),
        patch("src.agent.nodes.summarize.ChatOpenAI", return_value=mock_summarize_llm),
        patch("src.services.agent_runner.get_session_factory") as mock_factory,
        patch("src.agent.nodes.gather_context.run_history_agent", return_value="暂无相似历史事件"),
        patch("src.agent.nodes.gather_context.get_redis"),
    ):
        # Mock the session factory for _post_run DB operations
        mock_session = AsyncMock()
        mock_session.get.return_value = None  # No incident in DB during test
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_ctx)

        inc_id = "00000000-0000-0000-0000-000000000002"
        runner = AgentRunner(publisher=publisher, checkpointer=checkpointer)
        thread_id = await runner.start(
            incident_id=inc_id,
            title="Disk check",
            description="Routine disk check",
            severity="low",
            infrastructure_id=INFRA_ID,
            project_id="",
        )

    assert thread_id is not None
    # Should have published some events
    event_types = [e["event_type"] for e in published_events]
    assert len(published_events) > 0, "AgentRunner should have published events"
    # All events should be on the correct channel
    expected_channel = f"incident:{inc_id}"
    for e in published_events:
        assert e["channel"] == expected_channel
    # Should have summary event from _post_run
    assert "summary" in event_types, "AgentRunner should publish summary event"


async def test_agent_runner_creates_approval_record():
    """Test AgentRunner creates ApprovalRequest when agent needs approval."""
    import fakeredis.aioredis

    from src.agent.event_publisher import EventPublisher
    from src.services.agent_runner import AgentRunner

    checkpointer = MemorySaver()

    mock_ssh = make_mock_ssh()
    register_connector(INFRA_ID, mock_ssh)

    # Responses that trigger approval
    fake_responses = [
        AIMessage(
            content="Need to restart nginx",
            tool_calls=[
                {
                    "name": "exec_write_tool",
                    "args": {
                        "infra_id": INFRA_ID,
                        "command": "systemctl restart nginx",
                        "explanation": "重启 nginx",
                        "risk_level": "MEDIUM",
                        "risk_detail": "服务短暂中断",
                    },
                    "id": "tc-write-1",
                }
            ],
        ),
    ]
    fake_llm = FakeLLM(fake_responses)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    publisher = EventPublisher(redis=redis)

    published_events = []
    original_publish = publisher.publish

    async def capture_publish(channel, event_type, data):
        published_events.append({"channel": channel, "event_type": event_type, "data": data})
        await original_publish(channel, event_type, data)

    publisher.publish = capture_publish

    mock_approval = MagicMock()
    mock_approval.id = "approval-uuid-123"

    with (
        patch("src.agent.nodes.main_agent.get_llm", return_value=fake_llm),
        patch("src.services.agent_runner.get_session_factory") as mock_factory,
        patch("src.services.agent_runner.ApprovalService") as mock_approval_svc_cls,
        patch("src.agent.nodes.gather_context.run_history_agent", return_value="暂无相似历史事件"),
        patch("src.agent.nodes.gather_context.get_redis"),
    ):
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_ctx)

        mock_svc = AsyncMock()
        mock_svc.create.return_value = mock_approval
        mock_approval_svc_cls.return_value = mock_svc

        inc_id = "00000000-0000-0000-0000-000000000003"
        runner = AgentRunner(publisher=publisher, checkpointer=checkpointer)
        thread_id = await runner.start(
            incident_id=inc_id,
            title="Restart nginx",
            description="Need to restart",
            severity="high",
            infrastructure_id=INFRA_ID,
            project_id="",
        )

    # Verify approval was created with risk fields
    mock_svc.create.assert_called_once()
    call_kwargs = mock_svc.create.call_args.kwargs
    assert call_kwargs["risk_level"] == "MEDIUM"
    assert call_kwargs["explanation"] == "重启 nginx"

    # Verify approval_required event has approval_id
    approval_events = [e for e in published_events if e["event_type"] == "approval_required"]
    assert len(approval_events) == 1
    assert approval_events[0]["data"]["approval_id"] == "approval-uuid-123"
    assert approval_events[0]["data"]["tool_name"] == "exec_write_tool"
