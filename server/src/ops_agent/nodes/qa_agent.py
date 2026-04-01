"""QA Agent LLM 节点 —— 直接回答问题或执行简单任务，不走假设排查管线。"""

import time

from langchain_core.messages import SystemMessage

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent._llm import create_llm, invoke_with_retry, sanitize_response
from src.ops_agent.context import build_skills_context, build_system_prompt
from src.ops_agent.prompts.qa_agent import QA_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import MainState
from src.ops_agent.tools.base_tool import PermissionBehavior
from src.ops_agent.tools.registry import (
    APPROVAL_TOOL_NAMES,
    build_tool_guide_for_agent,
    build_tools_for_agent,
    get_tool,
)
from src.services.skill_service import SkillService


def build_qa_tools():
    """构建 QA Agent 的 LangChain 工具集。"""
    return build_tools_for_agent("qa")


async def qa_agent_node(state: MainState) -> dict:
    """QA Agent LLM 节点：直接回答问题或执行任务。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="qa", sid=sid)

    tools = build_qa_tools()
    llm = create_llm().bind_tools(tools)

    skill_service = SkillService()

    system_prompt = build_system_prompt(
        QA_AGENT_SYSTEM_PROMPT,
        description=state["description"],
        kb_summary=state.get("kb_summary"),
        skills=build_skills_context(skill_service),
        tool_guide=build_tool_guide_for_agent("qa"),
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    tool_names = [t.name for t in tools]
    log.info("qa_agent_node invoked", messages=len(messages), tools=tool_names)

    t0 = time.monotonic()
    response = await invoke_with_retry(llm, messages)
    elapsed = time.monotonic() - t0
    log.info("LLM responded", elapsed=f"{elapsed:.2f}s")

    safe_response = sanitize_response(response, set(tool_names), component="qa")
    return {"messages": [safe_response]}


async def route_qa_decision(state: MainState) -> str:
    """路由 QA Agent 的下一步。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="qa", sid=sid)

    last_message = state["messages"][-1]
    tools = build_qa_tools()
    valid_tool_names = {t.name for t in tools}

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        max_retries = get_settings().tool_call_max_retries
        retry_count = state.get("tool_call_retry_count", 0)
        if retry_count >= max_retries:
            log.info("no tool_calls after retries -> force complete")
            return "qa_complete"
        log.info("no tool_calls -> retry")
        return "qa_retry"

    for tc in last_message.tool_calls:
        name = tc["name"]
        if name not in valid_tool_names:
            log.warning("unknown tool -> retry", tool=name)
            return "qa_retry"
        if name == "complete":
            log.info("-> qa_complete")
            return "qa_complete"
        if name == "ask_human":
            log.info("-> qa_ask_human")
            return "qa_ask_human"
        # 权限检查
        if name in APPROVAL_TOOL_NAMES:
            tool_instance = get_tool(name)
            if tool_instance:
                perm = await tool_instance.check_permissions(**tc.get("args", {}))
                if perm.behavior in (PermissionBehavior.ASK, PermissionBehavior.DENY):
                    log.info("need_approval", tool=name)
                    return "qa_approval"

    log.info("-> qa_tools (continue)")
    return "qa_tools"
