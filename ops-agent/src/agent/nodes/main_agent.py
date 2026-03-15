from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from src.agent.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from src.agent.state import OpsState
from src.config import get_settings
from src.tools.exec_tools import exec_read, exec_write


def build_tools():
    from langchain_core.tools import tool

    @tool
    async def exec_read_tool(infra_id: str, command: str) -> dict:
        """Execute a read-only command on the target infrastructure.
        Use this for diagnostic commands like: df -h, free -m, ps aux, cat, etc.
        """
        return await exec_read(infra_id=infra_id, command=command)

    @tool
    async def exec_write_tool(infra_id: str, command: str) -> dict:
        """Execute a write command on the target infrastructure.
        This requires human approval. Use for commands like: systemctl restart, rm, mkdir, etc.
        """
        return await exec_write(infra_id=infra_id, command=command)

    @tool
    def complete(summary: str) -> str:
        """Call this when the investigation is complete. Provide a brief summary."""
        return summary

    return [exec_read_tool, exec_write_tool, complete]


def get_llm():
    s = get_settings()
    return ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )


async def main_agent_node(state: OpsState) -> dict:
    tools = build_tools()
    llm = get_llm().bind_tools(tools)

    system_prompt = MAIN_AGENT_SYSTEM_PROMPT.format(
        title=state["title"],
        description=state["description"],
        severity=state["severity"],
        infrastructure_id=state["infrastructure_id"],
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    response = await llm.ainvoke(messages)

    return {"messages": [response]}


def route_decision(state: OpsState) -> str:
    last_message = state["messages"][-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return "complete"

    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "complete":
            return "complete"
        if tool_call["name"] == "exec_write_tool":
            return "need_approval"

    return "continue"
