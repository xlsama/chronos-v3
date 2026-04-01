"""Compact 图节点 —— 主 Agent 和子 Agent 的上下文压缩。"""

from langchain_core.messages import HumanMessage, RemoveMessage

from src.lib.logger import get_logger
from src.ops_agent.context import compact_investigation_agent, compact_main_agent
from src.ops_agent.state import InvestigationState, MainState


async def main_compact_node(state: MainState) -> dict:
    """主 Agent 上下文压缩节点。

    1. 调用 mini_model 总结对话历史
    2. RemoveMessage 清除旧消息
    3. 添加一条新 HumanMessage 作为继续排查的起点
    4. 将 compact_md 存入 state
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="compact", sid=sid)
    log.info("===== Main compact started =====", messages=len(state["messages"]))

    summary = await compact_main_agent(
        incident_id=state["incident_id"],
        description=state["description"],
        severity=state["severity"],
        hypothesis_results=state.get("hypothesis_results") or [],
        messages=state["messages"],
    )

    log.info("===== Main compact completed =====", summary_chars=len(summary))

    # Remove all old messages + add a fresh starting message
    removals = [RemoveMessage(id=m.id) for m in state["messages"] if m.id]
    new_msg = HumanMessage(content="上下文已压缩，请根据排查进展摘要和当前调查计划继续排查。")

    return {
        "messages": removals + [new_msg],
        "compact_md": summary,
        "needs_compact": False,
        "tool_call_retry_count": 0,
    }


async def investigation_compact_node(state: InvestigationState) -> dict:
    """子 Agent 上下文压缩节点。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="compact", sid=sid)
    log.info(
        "===== Investigation compact started =====",
        hypothesis=state["hypothesis_id"],
        messages=len(state["messages"]),
    )

    summary = await compact_investigation_agent(
        incident_id=state["incident_id"],
        description=state["description"],
        severity=state["severity"],
        hypothesis_id=state["hypothesis_id"],
        hypothesis_desc=state["hypothesis_desc"],
        messages=state["messages"],
    )

    log.info("===== Investigation compact completed =====", summary_chars=len(summary))

    removals = [RemoveMessage(id=m.id) for m in state["messages"] if m.id]
    new_msg = HumanMessage(content="上下文已压缩，请根据排查进展摘要继续验证当前假设。")

    return {
        "messages": removals + [new_msg],
        "compact_md": summary,
        "needs_compact": False,
        "tool_call_retry_count": 0,
    }
