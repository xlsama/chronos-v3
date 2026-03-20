import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

from src.db.connection import get_session_factory
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.state import OpsState
from src.ops_agent.sub_agents.history_agent import run_history_agent
from src.ops_agent.sub_agents.kb_agent import KBAgentOutput, run_kb_agent
from src.lib.logger import get_logger
from src.lib.redis import get_redis

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


def _build_callback(channel: str, agent: str) -> tuple[EventCallback, EventPublisher | None]:
    """Build an event callback that publishes to Redis with phase/agent metadata."""
    if not channel:
        async def noop(event_type: str, data: dict) -> None:
            pass
        return noop, None

    redis = get_redis()
    publisher = EventPublisher(redis=redis, session_factory=get_session_factory())

    async def callback(event_type: str, data: dict) -> None:
        await publisher.publish(
            channel,
            event_type,
            {**data, "phase": "gather_context", "agent": agent},
        )

    return callback, publisher


async def _safe_run(coro_func, *args) -> Any:
    """Run a coroutine and return error string on failure instead of raising."""
    try:
        return await coro_func(*args)
    except Exception as e:
        get_logger().error("Sub-agent failed", func=coro_func.__name__, error=str(e))
        return f"[ERROR] {coro_func.__name__} 执行失败: {e}"


async def gather_context_node(state: OpsState) -> dict:
    """Run sub-agents to gather context before the main agent starts."""
    sid = state["incident_id"][:8]
    log = get_logger(component="gather_context", sid=sid)
    channel = EventPublisher.channel_for_incident(state["incident_id"])
    description = state["description"]

    log.info("===== Gathering context started =====")

    history_cb, history_pub = _build_callback(channel, agent="history")
    kb_cb, kb_pub = _build_callback(channel, agent="kb")

    await asyncio.gather(
        history_cb("agent_status", {"status": "started"}),
        kb_cb("agent_status", {"status": "started"}),
    )

    log.info("Starting parallel sub-agents: history + kb")
    t0 = time.monotonic()
    history_result, kb_result = await asyncio.gather(
        _safe_run(run_history_agent, description, history_cb),
        _safe_run(run_kb_agent, description, kb_cb),
    )
    parallel_elapsed = time.monotonic() - t0
    log.info("Parallel sub-agents completed", elapsed=f"{parallel_elapsed:.2f}s")

    if history_pub:
        await history_pub.flush_remaining(channel)
    if kb_pub:
        await kb_pub.flush_remaining(channel)

    history_failed = isinstance(history_result, str) and history_result.startswith("[ERROR]")
    kb_failed = isinstance(kb_result, str) and kb_result.startswith("[ERROR]")
    await asyncio.gather(
        history_cb("agent_status", {"status": "failed" if history_failed else "completed"}),
        kb_cb("agent_status", {"status": "failed" if kb_failed else "completed"}),
    )

    log.info("Sub-agents completed", history="FAILED" if history_failed else "OK", kb="FAILED" if kb_failed else "OK")

    if isinstance(history_result, str) and not history_failed:
        log.info("history_summary", chars=len(history_result))
        log.debug("history_summary preview", preview=history_result[:300])

    kb_summary = None
    kb_project_id = None
    if isinstance(kb_result, KBAgentOutput):
        if kb_result.project_id:
            kb_project_id = kb_result.project_id
        parts = []
        if kb_result.project_name:
            parts.append(f"匹配项目: {kb_result.project_name} (ID: {kb_result.project_id})")
        if kb_result.agents_md_content:
            parts.append(f"### AGENTS.md\n{kb_result.agents_md_content}")
        elif kb_result.agents_md_empty:
            parts.append("### AGENTS.md\n[空 - 未配置服务信息]")
        if kb_result.business_context:
            parts.append(f"### 业务背景\n{kb_result.business_context}")
        if kb_result.no_match:
            parts.append("未匹配到任何项目。")
        if kb_result.agents_md_empty:
            kb_summary = "\n\n".join(parts) + "\n\n[需要补充]"
        else:
            kb_summary = "\n\n".join(parts) if parts else None
    elif isinstance(kb_result, str):
        kb_summary = kb_result

    if kb_summary:
        log.info("kb_summary", chars=len(kb_summary), project_id=kb_project_id)
        log.debug("kb_summary preview", preview=kb_summary[:300])

    log.info("===== Gathering context completed =====")

    return {
        "incident_history_summary": history_result if isinstance(history_result, str) else None,
        "kb_summary": kb_summary,
        "kb_project_id": kb_project_id,
    }
