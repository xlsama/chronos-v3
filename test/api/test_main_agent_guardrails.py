from langchain_core.messages import AIMessage, HumanMessage

import pytest

from src.ops_agent.context_guardrails import build_context_request_question
from src.ops_agent.nodes import main_agent
from src.ops_agent.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from src.services.agent_runner import AgentRunner


pytestmark = pytest.mark.api


def _make_state(description: str) -> dict:
    return {
        "messages": [HumanMessage(content=f"事件描述: {description}")],
        "incident_id": "12345678-1234-5678-1234-567812345678",
        "description": description,
        "severity": "P2",
        "is_complete": False,
        "needs_approval": False,
        "pending_tool_call": None,
        "approval_decision": None,
        "ask_human_count": 0,
        "incident_history_summary": None,
        "kb_summary": None,
        "kb_project_id": None,
    }


def test_main_prompt_requires_ask_human_for_under_specified_input():
    assert "不要进入排查工具链，直接调用 ask_human 补充信息" in MAIN_AGENT_SYSTEM_PROMPT
    assert "当前输入只是问候/泛泛描述" in MAIN_AGENT_SYSTEM_PROMPT
    assert "按工具协议传参" in MAIN_AGENT_SYSTEM_PROMPT
    assert "不要把 SQL 关键字、MongoDB 子命令或 HTTP path 当成工具名" in MAIN_AGENT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_main_agent_node_sanitizes_unknown_tool_calls(monkeypatch):
    class StubLLM:
        def __init__(self, response: AIMessage):
            self.response = response

        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return self.response

    response = AIMessage(
        content="",
        tool_calls=[{"name": "find", "args": {}, "id": "call_find"}],
    )
    monkeypatch.setattr(main_agent, "get_llm", lambda: StubLLM(response))

    result = await main_agent.main_agent_node(_make_state("数据库连接超时"))

    message = result["messages"][0]
    assert isinstance(message, AIMessage)
    assert message.tool_calls == []
    assert build_context_request_question(["find"]) == message.content


@pytest.mark.asyncio
async def test_route_decision_rejects_unknown_tools():
    state = _make_state("数据库连接超时")
    state["messages"] = [
        AIMessage(content="", tool_calls=[{"name": "find", "args": {}, "id": "call_find"}]),
    ]

    assert await main_agent.route_decision(state) == "ask_human"


def test_agent_runner_formats_unknown_tool_error():
    message = AgentRunner._format_agent_error(KeyError("find"))
    assert "未注册的工具 `find`" in message
    assert "当前信息不足" in message
