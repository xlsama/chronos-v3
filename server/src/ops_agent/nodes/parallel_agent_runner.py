"""并行子 Agent 生命周期管理节点 —— asyncio.TaskGroup 并发执行多个 investigation 子 Agent。"""

import asyncio
import uuid

from langchain_core.messages import HumanMessage, ToolMessage

from src.db.connection import get_session_factory
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.nodes.agent_runner import (
    _create_and_publish_approval,
    _extract_findings,
    _format_prior_findings,
    _resume_sub_agent,
    _stream_sub_agent,
)
from src.ops_agent.state import ActiveAgent, HypothesisResult, MainState
from src.ops_agent.agents.investigation_graph import compile_investigation_graph
from src.services.notification_service import notify_fire_and_forget

MAX_PARALLEL = 3


# ═══════════════════════════════════════════
# 提取 spawn_parallel_agents 参数
# ═══════════════════════════════════════════


def _extract_parallel_launch_info(state: MainState) -> tuple[list[dict], str]:
    """从最近的 spawn_parallel_agents tool_call 提取假设列表和 tool_call_id。"""
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "spawn_parallel_agents":
                    args = tc.get("args", {})
                    return args.get("hypotheses", []), tc["id"]
            break
    return [], ""


# ═══════════════════════════════════════════
# 单个子 Agent 执行（供 TaskGroup 调用）
# ═══════════════════════════════════════════


async def _run_single_sub_agent(
    hypothesis: dict,
    state: MainState,
    prior_findings: str,
    checkpointer,
    channel: str,
    publisher: EventPublisher,
    log,
) -> ActiveAgent:
    """运行单个子 Agent，返回 ActiveAgent 跟踪状态。"""
    hypothesis_id = hypothesis.get("hypothesis_id", "H1")
    hypothesis_title = hypothesis.get("hypothesis_title", "")
    hypothesis_desc = hypothesis.get("hypothesis_desc", "")

    sub_graph = compile_investigation_graph(checkpointer=checkpointer)
    sub_thread_id = str(uuid.uuid4())

    initial_prompt = (
        f"事件描述: {state['description']}\n\n请验证假设 {hypothesis_id}: {hypothesis_desc}"
    )

    initial_state = {
        "messages": [HumanMessage(content=initial_prompt)],
        "incident_id": state["incident_id"],
        "description": state["description"],
        "severity": state["severity"],
        "hypothesis_id": hypothesis_id,
        "hypothesis_desc": hypothesis_desc,
        "prior_findings": prior_findings,
        "kb_summary": state.get("kb_summary"),
        "is_complete": False,
        "needs_approval": False,
        "pending_tool_call": None,
        "approval_decision": None,
        "approval_supplement": None,
        "ask_human_count": 0,
        "tool_call_retry_count": 0,
    }

    config = {
        "configurable": {"thread_id": sub_thread_id},
        "recursion_limit": get_settings().agent_recursion_limit,
    }

    # 发布 agent_started 事件
    try:
        await publisher.publish(
            channel,
            "agent_started",
            {
                "hypothesis_id": hypothesis_id,
                "hypothesis_title": hypothesis_title,
                "hypothesis_desc": hypothesis_desc,
                "sub_agent_thread_id": sub_thread_id,
                "phase": "investigation",
            },
        )
    except Exception as e:
        log.warning("Failed to publish agent_started", error=str(e))

    # 执行子 Agent
    try:
        result = await _stream_sub_agent(
            sub_graph, initial_state, config, channel, publisher, hypothesis_id, log
        )
    except Exception as e:
        log.error("Sub-agent failed", hypothesis=hypothesis_id, error=str(e))
        return ActiveAgent(
            thread_id=sub_thread_id,
            hypothesis_id=hypothesis_id,
            hypothesis_title=hypothesis_title,
            hypothesis_desc=hypothesis_desc,
            status="failed",
            result=HypothesisResult(
                hypothesis_id=hypothesis_id,
                hypothesis_desc=hypothesis_desc,
                status="inconclusive",
                summary=f"排查异常: {str(e)[:200]}",
                detail="",
            ),
            pending_tool_call=None,
            pending_approval_id=None,
        )

    # 子 Agent hit interrupt
    if result["needs_interrupt"]:
        interrupt_type = result["interrupt_type"]
        return ActiveAgent(
            thread_id=sub_thread_id,
            hypothesis_id=hypothesis_id,
            hypothesis_title=hypothesis_title,
            hypothesis_desc=hypothesis_desc,
            status=f"interrupted_{interrupt_type}",
            result=None,
            pending_tool_call=result.get("pending_tool_call"),
            pending_approval_id=None,
        )

    # 子 Agent 完成 → 提取结果
    hypothesis_info = {"id": hypothesis_id, "title": hypothesis_title, "desc": hypothesis_desc}
    finding = await _extract_findings(sub_graph, config, hypothesis_info)
    log.info("Sub-agent completed", hypothesis=hypothesis_id, status=finding["status"])

    try:
        await publisher.publish(
            channel,
            "agent_completed",
            {
                "hypothesis_id": hypothesis_id,
                "status": finding["status"],
                "summary": finding["summary"][:500],
                "phase": "investigation",
            },
        )
    except Exception as e:
        log.warning("Failed to publish agent_completed", error=str(e))

    return ActiveAgent(
        thread_id=sub_thread_id,
        hypothesis_id=hypothesis_id,
        hypothesis_title=hypothesis_title,
        hypothesis_desc=hypothesis_desc,
        status="completed",
        result=finding,
        pending_tool_call=None,
        pending_approval_id=None,
    )


# ═══════════════════════════════════════════
# 结果收集和构造返回值
# ═══════════════════════════════════════════

_STATUS_ZH = {"confirmed": "已确认", "eliminated": "已排除", "inconclusive": "证据不足"}


def _find_first_interrupted(agents: list[ActiveAgent]) -> ActiveAgent | None:
    """找到第一个中断的子 Agent。"""
    for a in agents:
        if a["status"].startswith("interrupted_"):
            return a
    return None


def _build_final_tool_message(
    agents: list[ActiveAgent], tool_call_id: str
) -> ToolMessage:
    """将所有子 Agent 结果合并为一条 ToolMessage。"""
    parts = []
    for a in agents:
        r = a.get("result")
        if r:
            status_zh = _STATUS_ZH.get(r["status"], r["status"])
            parts.append(
                f"假设 {r['hypothesis_id']} 调查完成。\n"
                f"状态: {status_zh}\n"
                f"摘要: {r['summary']}\n\n"
                f"{r['detail']}"
            )
        elif a["status"] == "failed":
            parts.append(f"假设 {a['hypothesis_id']} 排查异常。")
    return ToolMessage(content="\n\n---\n\n".join(parts), tool_call_id=tool_call_id)


def _collect_all_findings(agents: list[ActiveAgent]) -> list[HypothesisResult]:
    """收集所有已完成的 HypothesisResult。"""
    return [a["result"] for a in agents if a.get("result")]


# ═══════════════════════════════════════════
# 主入口节点
# ═══════════════════════════════════════════


async def run_parallel_agents_node(state: MainState) -> dict:
    """并行执行多个子 Agent。

    首次进入：并发启动所有子 Agent，等待全部完成或中断。
    恢复进入：只恢复被中断的那个子 Agent。
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="parallel_agents", sid=sid)
    incident_id = state["incident_id"]
    existing_results = list(state.get("hypothesis_results") or [])
    parallel_agents = list(state.get("parallel_agents") or [])

    from src.main import get_checkpointer

    checkpointer = get_checkpointer()

    channel = EventPublisher.channel_for_incident(incident_id)
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())

    is_resume = bool(parallel_agents) and any(
        a["status"].startswith("interrupted_") for a in parallel_agents
    )

    if is_resume:
        return await _handle_resume(
            state, parallel_agents, existing_results,
            checkpointer, channel, publisher, log,
        )
    else:
        return await _handle_first_run(
            state, existing_results,
            checkpointer, channel, publisher, log,
        )


async def _handle_first_run(
    state: MainState,
    existing_results: list[HypothesisResult],
    checkpointer,
    channel: str,
    publisher: EventPublisher,
    log,
) -> dict:
    """首次进入：提取假设列表，asyncio.TaskGroup 并发执行。"""
    hypotheses, tool_call_id = _extract_parallel_launch_info(state)
    hypotheses = hypotheses[:MAX_PARALLEL]

    if not hypotheses:
        log.warning("No hypotheses to investigate")
        return {
            "messages": [
                ToolMessage(content="未提供假设列表。", tool_call_id=tool_call_id)
            ],
        }

    log.info("Starting parallel investigation", count=len(hypotheses))
    prior_findings = _format_prior_findings(existing_results)

    # 并发执行所有子 Agent
    agents: list[ActiveAgent] = []
    errors: list[Exception] = []

    async def _safe_run(h: dict) -> ActiveAgent:
        return await _run_single_sub_agent(
            h, state, prior_findings, checkpointer, channel, publisher, log,
        )

    # 用 gather 而非 TaskGroup，因为 TaskGroup 在任一 task 异常时取消全部
    tasks = [asyncio.create_task(_safe_run(h)) for h in hypotheses]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, r in enumerate(results):
        if isinstance(r, Exception):
            h = hypotheses[i]
            log.error("Sub-agent task exception", hypothesis=h.get("hypothesis_id"), error=str(r))
            errors.append(r)
            agents.append(ActiveAgent(
                thread_id="",
                hypothesis_id=h.get("hypothesis_id", f"H{i+1}"),
                hypothesis_title=h.get("hypothesis_title", ""),
                hypothesis_desc=h.get("hypothesis_desc", ""),
                status="failed",
                result=HypothesisResult(
                    hypothesis_id=h.get("hypothesis_id", f"H{i+1}"),
                    hypothesis_desc=h.get("hypothesis_desc", ""),
                    status="inconclusive",
                    summary=f"排查异常: {str(r)[:200]}",
                    detail="",
                ),
                pending_tool_call=None,
                pending_approval_id=None,
            ))
        else:
            agents.append(r)

    log.info(
        "Parallel investigation phase done",
        completed=sum(1 for a in agents if a["status"] == "completed"),
        interrupted=sum(1 for a in agents if a["status"].startswith("interrupted_")),
        failed=sum(1 for a in agents if a["status"] == "failed"),
    )

    # 检查是否有中断需要处理
    first_interrupted = _find_first_interrupted(agents)
    if first_interrupted:
        return await _prepare_interrupt(
            agents, first_interrupted, existing_results,
            tool_call_id, state, publisher, channel, log,
        )

    # 全部完成（或失败）→ 返回批量 ToolMessage
    all_findings = existing_results + _collect_all_findings(agents)
    return {
        "messages": [_build_final_tool_message(agents, tool_call_id)],
        "hypothesis_results": all_findings,
        "parallel_agents": [],
        "parallel_launch_tool_call_id": None,
        "parallel_interrupted_agent_id": None,
        "agent_status": "completed",
        "needs_approval": False,
        "pending_tool_call": None,
        "pending_approval_id": None,
    }


async def _handle_resume(
    state: MainState,
    parallel_agents: list[ActiveAgent],
    existing_results: list[HypothesisResult],
    checkpointer,
    channel: str,
    publisher: EventPublisher,
    log,
) -> dict:
    """恢复被中断的子 Agent，完成后检查是否还有其他中断。"""
    interrupted_id = state.get("parallel_interrupted_agent_id")
    tool_call_id = state.get("parallel_launch_tool_call_id", "")

    agent_info = None
    for a in parallel_agents:
        if a["hypothesis_id"] == interrupted_id:
            agent_info = a
            break

    if not agent_info:
        log.warning("Cannot find interrupted agent to resume", id=interrupted_id)
        all_findings = existing_results + _collect_all_findings(parallel_agents)
        return {
            "messages": [_build_final_tool_message(parallel_agents, tool_call_id)],
            "hypothesis_results": all_findings,
            "parallel_agents": [],
            "parallel_launch_tool_call_id": None,
            "parallel_interrupted_agent_id": None,
            "agent_status": "completed",
        }

    hypothesis_id = agent_info["hypothesis_id"]
    log.info("Resuming interrupted sub-agent", hypothesis=hypothesis_id)

    sub_graph = compile_investigation_graph(checkpointer=checkpointer)
    config = {
        "configurable": {"thread_id": agent_info["thread_id"]},
        "recursion_limit": get_settings().agent_recursion_limit,
    }

    # 传递 approval_id 用于标记 resume 后的 tool_use 事件
    approval_id_for_resume = ""
    if state.get("approval_decision") == "approved" and state.get("pending_approval_id"):
        approval_id_for_resume = state["pending_approval_id"]

    try:
        result = await _resume_sub_agent(
            sub_graph, config, state, channel, publisher,
            hypothesis_id, log, approval_id=approval_id_for_resume,
        )
    except Exception as e:
        log.error("Sub-agent resume failed", hypothesis=hypothesis_id, error=str(e))
        # 标记为 failed，继续处理其他中断
        agent_info["status"] = "failed"
        agent_info["result"] = HypothesisResult(
            hypothesis_id=hypothesis_id,
            hypothesis_desc=agent_info["hypothesis_desc"],
            status="inconclusive",
            summary=f"恢复排查异常: {str(e)[:200]}",
            detail="",
        )
        # 检查下一个中断
        next_interrupted = _find_first_interrupted(parallel_agents)
        if next_interrupted:
            return await _prepare_interrupt(
                parallel_agents, next_interrupted, existing_results,
                tool_call_id, state, publisher, channel, log,
            )
        all_findings = existing_results + _collect_all_findings(parallel_agents)
        return {
            "messages": [_build_final_tool_message(parallel_agents, tool_call_id)],
            "hypothesis_results": all_findings,
            "parallel_agents": [],
            "parallel_launch_tool_call_id": None,
            "parallel_interrupted_agent_id": None,
            "agent_status": "completed",
        }

    if result["needs_interrupt"]:
        # 再次中断 → 更新状态
        interrupt_type = result["interrupt_type"]
        agent_info["status"] = f"interrupted_{interrupt_type}"
        agent_info["pending_tool_call"] = result.get("pending_tool_call")
        return await _prepare_interrupt(
            parallel_agents, agent_info, existing_results,
            tool_call_id, state, publisher, channel, log,
        )

    # 完成 → 提取结果
    hypothesis_info = {
        "id": hypothesis_id,
        "title": agent_info["hypothesis_title"],
        "desc": agent_info["hypothesis_desc"],
    }
    finding = await _extract_findings(sub_graph, config, hypothesis_info)
    log.info("Resumed sub-agent completed", hypothesis=hypothesis_id, status=finding["status"])

    agent_info["status"] = "completed"
    agent_info["result"] = finding

    try:
        await publisher.publish(
            channel,
            "agent_completed",
            {
                "hypothesis_id": hypothesis_id,
                "status": finding["status"],
                "summary": finding["summary"][:500],
                "phase": "investigation",
            },
        )
    except Exception as e:
        log.warning("Failed to publish agent_completed", error=str(e))

    # 检查是否还有其他中断的 agent
    next_interrupted = _find_first_interrupted(parallel_agents)
    if next_interrupted:
        return await _prepare_interrupt(
            parallel_agents, next_interrupted, existing_results,
            tool_call_id, state, publisher, channel, log,
        )

    # 全部完成 → 返回结果
    all_findings = existing_results + _collect_all_findings(parallel_agents)
    return {
        "messages": [_build_final_tool_message(parallel_agents, tool_call_id)],
        "hypothesis_results": all_findings,
        "parallel_agents": [],
        "parallel_launch_tool_call_id": None,
        "parallel_interrupted_agent_id": None,
        "agent_status": "completed",
        "needs_approval": False,
        "pending_tool_call": None,
        "pending_approval_id": None,
    }


# ═══════════════════════════════════════════
# 中断准备
# ═══════════════════════════════════════════


async def _prepare_interrupt(
    parallel_agents: list[ActiveAgent],
    interrupted_agent: ActiveAgent,
    existing_results: list[HypothesisResult],
    tool_call_id: str,
    state: MainState,
    publisher: EventPublisher,
    channel: str,
    log,
) -> dict:
    """准备中断返回值，创建审批记录（如需要）。"""
    hypothesis_id = interrupted_agent["hypothesis_id"]
    interrupt_type = interrupted_agent["status"]  # "interrupted_human_approval" or "interrupted_ask_human"

    log.info("Sub-agent hit interrupt", hypothesis=hypothesis_id, type=interrupt_type)

    return_state: dict = {
        "parallel_agents": parallel_agents,
        "parallel_launch_tool_call_id": tool_call_id,
        "parallel_interrupted_agent_id": hypothesis_id,
        "agent_status": "waiting_for_human",
    }

    if interrupt_type == "interrupted_human_approval":
        pending = interrupted_agent.get("pending_tool_call")
        approval_id = await _create_and_publish_approval(
            publisher, channel, pending,
            state["incident_id"], state["description"], state["severity"],
            hypothesis_id, log,
        )
        interrupted_agent["pending_approval_id"] = approval_id
        return_state["needs_approval"] = True
        return_state["pending_tool_call"] = pending
        return_state["pending_approval_id"] = approval_id
    elif interrupt_type == "interrupted_ask_human":
        return_state["needs_approval"] = False
        return_state["pending_tool_call"] = None
        return_state["pending_approval_id"] = None
        notify_fire_and_forget(
            "ask_human",
            state["incident_id"],
            state.get("description", "")[:80],
            severity=state.get("severity", ""),
            question="（并行子 Agent 提问）",
        )

    return return_state
