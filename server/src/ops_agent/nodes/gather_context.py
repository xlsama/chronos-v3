import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

from src.db.connection import get_session_factory
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.state import OpsState
from src.ops_agent.sub_agents.history_agent import run_history_agent
from src.ops_agent.sub_agents.kb_agent import KBAgentOutput, run_kb_agent
from src.lib.logger import logger
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
        logger.error(f"{coro_func.__name__} failed: {e}")
        return f"[ERROR] {coro_func.__name__} 执行失败: {e}"


async def gather_context_node(state: OpsState) -> dict:
    """Run sub-agents to gather context before the main agent starts."""
    sid = state["incident_id"][:8]
    channel = EventPublisher.channel_for_incident(state["incident_id"])
    description = state["description"]

    logger.info(f"\n[{sid}] [gather_context] ===== Gathering context started =====")

    history_cb, history_pub = _build_callback(channel, agent="history")
    kb_cb, kb_pub = _build_callback(channel, agent="kb")

    # Publish agent_status started (parallel to minimize UI flicker)
    await asyncio.gather(
        history_cb("agent_status", {"status": "started"}),
        kb_cb("agent_status", {"status": "started"}),
    )

    # Run both sub-agents in parallel
    logger.info(f"[{sid}] [gather_context] Starting parallel sub-agents: history + kb")
    t0 = time.monotonic()
    history_result, kb_result = await asyncio.gather(
        _safe_run(run_history_agent, description, history_cb),
        _safe_run(run_kb_agent, description, kb_cb),
    )
    parallel_elapsed = time.monotonic() - t0
    logger.info(f"[{sid}] [gather_context] Parallel sub-agents completed in {parallel_elapsed:.2f}s")

    # Flush sub-agent thinking buffers so all thinking events are persisted
    if history_pub:
        await history_pub.flush_remaining(channel)
    if kb_pub:
        await kb_pub.flush_remaining(channel)

    # Publish agent_status completed/failed
    history_failed = isinstance(history_result, str) and history_result.startswith("[ERROR]")
    kb_failed = isinstance(kb_result, str) and kb_result.startswith("[ERROR]")
    await asyncio.gather(
        history_cb("agent_status", {"status": "failed" if history_failed else "completed"}),
        kb_cb("agent_status", {"status": "failed" if kb_failed else "completed"}),
    )

    logger.info(f"[{sid}] [gather_context] Sub-agents completed: history={'FAILED' if history_failed else 'OK'}, kb={'FAILED' if kb_failed else 'OK'}")

    # Log history summary details
    if isinstance(history_result, str) and not history_failed:
        logger.info(f"[{sid}] [gather_context] history_summary: {len(history_result)} chars")
        logger.debug(f"[{sid}] [gather_context] history_summary preview:\n{history_result[:300]}")

    # Extract KB result
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
        kb_summary = kb_result  # Error case

    if kb_summary:
        logger.info(f"[{sid}] [gather_context] kb_summary: {len(kb_summary)} chars, project_id={kb_project_id}")
        logger.debug(f"[{sid}] [gather_context] kb_summary preview:\n{kb_summary[:300]}")

    logger.info(f"\n[{sid}] [gather_context] ===== Gathering context completed =====")

    return {
        "incident_history_summary": history_result if isinstance(history_result, str) else None,
        "kb_summary": kb_summary,
        "kb_project_id": kb_project_id,
    }
