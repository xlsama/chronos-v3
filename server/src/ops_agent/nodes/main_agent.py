"""主 Agent LLM 节点 —— 调度子 Agent、评估结果、更新计划、向用户提问、输出结论。"""

import time

from langchain_core.messages import SystemMessage

from src.db.connection import get_session_factory
from src.db.models import Incident
from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent._llm import create_llm, invoke_with_retry, sanitize_response
from src.ops_agent.context import (
    build_skills_context,
    build_system_prompt,
    is_context_limit_error,
    should_proactive_compact,
)
from src.ops_agent.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import MainState
from src.ops_agent.tools.registry import build_tool_guide_for_agent, build_tools_for_agent
from src.services.skill_service import SkillService


def build_main_tools():
    """构建主 Agent 的 LangChain 工具集。"""
    return build_tools_for_agent("main")


async def _build_plan_context(incident_id: str) -> str | None:
    """从 DB 读取调查计划。返回纯计划内容或 None。"""
    import uuid

    try:
        async with get_session_factory()() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if incident and incident.plan_md:
                return incident.plan_md
    except Exception:
        pass
    return None


async def main_agent_node(state: MainState) -> dict:
    """主 Agent LLM 节点。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="main", sid=sid)

    tools = build_main_tools()
    llm = create_llm().bind_tools(tools)

    # 构建上下文
    plan_context = await _build_plan_context(state["incident_id"])
    skill_service = SkillService()

    system_prompt = build_system_prompt(
        MAIN_AGENT_SYSTEM_PROMPT,
        description=state["description"],
        severity=state["severity"],
        incident_history=state.get("incident_history_summary"),
        kb_summary=state.get("kb_summary"),
        plan=plan_context,
        skills=build_skills_context(skill_service),
        compact_md=state.get("compact_md"),
        tool_guide=build_tool_guide_for_agent("main"),
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    # 主动 compact：在 LLM 调用前检查消息量，避免浪费一次失败的 API 调用
    if should_proactive_compact(messages):
        log.info("Proactive compact triggered", messages=len(messages))
        return {"needs_compact": True}

    tool_names = [t.name for t in tools]
    log.info(
        "main_agent_node invoked",
        messages=len(messages),
        tools=tool_names,
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

    content_text = response.content if hasattr(response, "content") else ""
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    log.info("LLM response", content_len=len(content_text), tool_calls=len(tool_calls))
    if content_text:
        log.info("LLM content", content=content_text)
    for tc in tool_calls:
        log.info("LLM tool_call", name=tc["name"], args=tc.get("args", {}))

    safe_response = sanitize_response(response, set(tool_names), component="main")

    # 保存 tool_call_id 用于 ToolMessage 回复
    result: dict = {"messages": [safe_response]}
    if hasattr(safe_response, "tool_calls") and safe_response.tool_calls:
        for tc in safe_response.tool_calls:
            if tc["name"] == "spawn_agent":
                result["pending_spawn_tool_call_id"] = tc["id"]
                break
            if tc["name"] == "spawn_verification":
                result["pending_verify_tool_call_id"] = tc["id"]
                break
            if tc["name"] == "spawn_parallel_agents":
                result["parallel_launch_tool_call_id"] = tc["id"]
                break

    return result


async def route_main_decision(state: MainState) -> str:
    """路由主 Agent 的下一步。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="main", sid=sid)

    if state.get("needs_compact"):
        log.info("-> compact (context limit reached)")
        return "compact"

    last_message = state["messages"][-1]
    tools = build_main_tools()
    valid_tool_names = {t.name for t in tools}

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        max_retries = get_settings().tool_call_max_retries
        retry_count = state.get("tool_call_retry_count", 0)
        if retry_count >= max_retries:
            if state.get("ask_human_count", 0) >= 5:
                log.info("no tool_calls after retries, ask_human exhausted -> force complete")
                return "complete"
            log.info("no tool_calls after retries -> ask_human (fallback)")
            return "ask_human"
        log.info("no tool_calls -> retry_tool_call")
        return "retry_tool_call"

    for tc in last_message.tool_calls:
        name = tc["name"]
        if name not in valid_tool_names:
            log.warning("unknown tool -> retry", tool=name)
            return "retry_tool_call"
        if name == "complete":
            log.info("-> confirm_resolution")
            return "complete"
        if name == "ask_human":
            if state.get("ask_human_count", 0) >= 5:
                log.warning("ask_human count exceeded limit, forcing complete")
                return "complete"
            log.info("-> ask_human")
            return "ask_human"
        if name == "spawn_agent":
            log.info("-> run_agent", hypothesis=tc["args"].get("hypothesis_id"))
            return "spawn_agent"
        if name == "spawn_verification":
            log.info("-> run_verification")
            return "spawn_verification"
        if name == "spawn_parallel_agents":
            hypotheses = tc["args"].get("hypotheses", [])
            log.info("-> run_parallel_agents", count=len(hypotheses))
            return "spawn_parallel"

    # update_plan 等其他工具 → tools (ToolNode)
    log.info("-> tools (continue)")
    return "continue"
