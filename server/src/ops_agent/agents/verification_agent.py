"""Verification Agent 的 LLM 节点 —— 验证排查结论是否正确。"""

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
from src.ops_agent.prompts.verification_agent import VERIFICATION_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import VerificationState
from src.ops_agent.tools.base_tool import PermissionBehavior
from src.ops_agent.tools.registry import (
    APPROVAL_TOOL_NAMES,
    build_tool_guide_for_agent,
    build_tools_for_agent,
    get_tool,
)
from src.services.skill_service import SkillService


def build_verification_tools():
    """构建 Verification Agent 的 LangChain 工具集。"""
    return build_tools_for_agent("verification")


def _format_hypothesis_results(results: list[dict]) -> str:
    """将 hypothesis_results 格式化为摘要文本。"""
    if not results:
        return "无"
    lines = []
    for r in results:
        status_map = {"confirmed": "已确认", "eliminated": "已排除", "inconclusive": "证据不足"}
        status_zh = status_map.get(r.get("status", ""), r.get("status", ""))
        lines.append(
            f"- {r.get('hypothesis_id', '?')} [{status_zh}] "
            f"{r.get('hypothesis_desc', '')}: {r.get('summary', '')}"
        )
    return "\n".join(lines)


async def verification_agent_node(state: VerificationState) -> dict:
    """Verification Agent LLM 节点：验证排查结论。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="verification", sid=sid)

    tools = build_verification_tools()
    llm = create_llm().bind_tools(tools)

    skill_service = SkillService()
    results_summary = _format_hypothesis_results(state.get("hypothesis_results") or [])

    system_prompt = build_system_prompt(
        VERIFICATION_AGENT_SYSTEM_PROMPT,
        description=state["description"],
        severity=state["severity"],
        kb_summary=state.get("kb_summary"),
        skills=build_skills_context(skill_service),
        compact_md=state.get("compact_md"),
        answer_md=state.get("answer_md", ""),
        hypothesis_results_summary=results_summary,
        tool_guide=build_tool_guide_for_agent("verification"),
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    if should_proactive_compact(messages):
        log.info("Proactive compact triggered", messages=len(messages))
        return {"needs_compact": True}

    tool_names = [t.name for t in tools]
    log.info("verification_agent_node invoked", messages=len(messages))

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

    safe_response = sanitize_response(response, set(tool_names), component="verification")
    return {"messages": [safe_response]}


async def route_verification_decision(state: VerificationState) -> str:
    """路由 Verification Agent 的下一步。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="verification", sid=sid)

    if state.get("needs_compact"):
        log.info("-> compact (context limit reached)")
        return "compact"

    last_message = state["messages"][-1]
    tools = build_verification_tools()
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
        if name == "submit_verification":
            log.info("tool=submit_verification -> complete")
            return "complete"
        if name == "ask_human":
            if state.get("ask_human_count", 0) >= 5:
                log.warning("ask_human count exceeded, forcing complete")
                return "complete"
            log.info("tool=ask_human -> ask_human")
            return "ask_human"

        if name in APPROVAL_TOOL_NAMES:
            tool_instance = get_tool(name)
            if tool_instance:
                perm = await tool_instance.check_permissions(**tc.get("args", {}))
                if perm.behavior == PermissionBehavior.DENY:
                    log.info("need_approval", tool=name)
                    return "need_approval"
                if perm.behavior == PermissionBehavior.ASK:
                    explanation = tc.get("args", {}).get("explanation", "").strip()
                    if not explanation:
                        log.info("missing_explanation", tool=name)
                        return "missing_explanation"
                    log.info("need_approval", tool=name)
                    return "need_approval"

    log.info("-> continue")
    return "continue"
