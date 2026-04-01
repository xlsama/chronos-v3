"""子 Agent 的 LLM 节点 —— 专注验证单个假设。"""

import time

from langchain_core.messages import SystemMessage

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent._llm import create_llm, invoke_with_retry, sanitize_response
from src.ops_agent.context import (
    build_skills_context,
    build_system_prompt,
    is_context_limit_error,
    should_proactive_compact,
)
from src.ops_agent.prompts.investigation_agent import INVESTIGATION_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import InvestigationState
from src.ops_agent.tools.base_tool import PermissionBehavior
from src.ops_agent.tools.registry import (
    APPROVAL_TOOL_NAMES,
    build_tool_guide_for_agent,
    build_tools_for_agent,
    get_tool,
)
from src.services.skill_service import SkillService


def build_investigation_tools():
    """构建子 Agent 的 LangChain 工具集。"""
    return build_tools_for_agent("investigation")


async def investigation_agent_node(state: InvestigationState) -> dict:
    """子 Agent LLM 节点：验证单个假设。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="investigation", sid=sid)

    tools = build_investigation_tools()
    llm = create_llm().bind_tools(tools)

    # 构建上下文
    skill_service = SkillService()

    system_prompt = build_system_prompt(
        INVESTIGATION_AGENT_SYSTEM_PROMPT,
        description=state["description"],
        severity=state["severity"],
        kb_summary=state.get("kb_summary"),
        skills=build_skills_context(skill_service),
        compact_md=state.get("compact_md"),
        prior_findings=state.get("prior_findings") or None,
        hypothesis_id=state["hypothesis_id"],
        hypothesis_desc=state["hypothesis_desc"],
        tool_guide=build_tool_guide_for_agent("investigation"),
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    # 主动 compact：在 LLM 调用前检查消息量，避免浪费一次失败的 API 调用
    if should_proactive_compact(messages):
        log.info("Proactive compact triggered", messages=len(messages))
        return {"needs_compact": True}

    tool_names = [t.name for t in tools]
    log.info(
        "investigation_agent_node invoked",
        hypothesis=state["hypothesis_id"],
        messages=len(messages),
    )

    t0 = time.monotonic()
    try:
        response = await invoke_with_retry(llm, messages)
    except Exception as e:
        if is_context_limit_error(e):
            log.warning("Context limit reached, triggering compact", error=str(e))
            return {"needs_compact": True}
        raise
    elapsed = time.monotonic() - t0
    log.info("LLM responded", elapsed=f"{elapsed:.2f}s")

    safe_response = sanitize_response(response, set(tool_names), component="investigation")
    return {"messages": [safe_response]}


async def route_investigation_decision(state: InvestigationState) -> str:
    """路由子 Agent 的下一步。

    权限检查统一委托给 tool.check_permissions()，不再内嵌分类器逻辑。
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="investigation", sid=sid)

    if state.get("needs_compact"):
        log.info("-> compact (context limit reached)")
        return "compact"

    last_message = state["messages"][-1]
    tools = build_investigation_tools()
    valid_tool_names = {t.name for t in tools}

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        if state.get("ask_human_count", 0) >= 5:
            log.warning("ask_human count exceeded, forcing complete")
            return "complete"

        max_retries = get_settings().tool_call_max_retries
        retry_count = state.get("tool_call_retry_count", 0)
        if retry_count >= max_retries:
            log.info("no tool_calls after retries -> ask_human")
            return "ask_human"

        log.info("no tool_calls -> retry_tool_call")
        return "retry_tool_call"

    for tc in last_message.tool_calls:
        name = tc["name"]
        if name not in valid_tool_names:
            log.warning("unknown tool -> ask_human", tool=name)
            return "ask_human"
        if name == "conclude":
            log.info("tool=conclude -> complete")
            return "complete"
        if name == "ask_human":
            if state.get("ask_human_count", 0) >= 5:
                log.warning("ask_human count exceeded, forcing complete")
                return "complete"
            log.info("tool=ask_human -> ask_human")
            return "ask_human"

        # 统一权限检查：委托给 tool.check_permissions()
        if name in APPROVAL_TOOL_NAMES:
            tool_instance = get_tool(name)
            if tool_instance:
                perm = await tool_instance.check_permissions(**tc.get("args", {}))
                if perm.behavior in (PermissionBehavior.ASK, PermissionBehavior.DENY):
                    log.info(
                        "need_approval",
                        tool=name,
                        behavior=perm.behavior.value,
                        risk_level=perm.risk_level,
                    )
                    return "need_approval"

    log.info("-> continue")
    return "continue"
