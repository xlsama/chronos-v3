import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

from src.db.connection import get_session_factory
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.state import MainState
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


async def gather_context_node(state: MainState) -> dict:
    """Run sub-agents to gather context before the main agent starts."""
    sid = state["incident_id"][:8]
    log = get_logger(component="gather_context", sid=sid)
    channel = EventPublisher.channel_for_incident(state["incident_id"])
    description = state["description"]

    intent = state.get("intent", "incident")
    skip_history = intent in ("question", "task")

    log.info("===== Gathering context started =====", intent=intent, skip_history=skip_history)

    kb_cb, kb_pub = _build_callback(channel, agent="kb")
    await kb_cb("agent_status", {"status": "started"})

    history_result = None
    if skip_history:
        # question/task 不需要历史事件参考，只跑 KB
        log.info("Skipping history agent (intent=%s)", intent)
        t0 = time.monotonic()
        kb_result = await _safe_run(run_kb_agent, description, kb_cb)
        elapsed = time.monotonic() - t0
        log.info("KB agent completed", elapsed=f"{elapsed:.2f}s")
    else:
        history_cb, history_pub = _build_callback(channel, agent="history")
        await history_cb("agent_status", {"status": "started"})

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

        history_failed = isinstance(history_result, str) and history_result.startswith("[ERROR]")
        await history_cb("agent_status", {"status": "failed" if history_failed else "completed"})
        log.info("History agent", status="FAILED" if history_failed else "OK")

    if kb_pub:
        await kb_pub.flush_remaining(channel)
    kb_failed = isinstance(kb_result, str) and kb_result.startswith("[ERROR]")
    await kb_cb("agent_status", {"status": "failed" if kb_failed else "completed"})
    log.info("KB agent", status="FAILED" if kb_failed else "OK")

    history_is_valid = isinstance(history_result, str) and not history_result.startswith("[ERROR]")
    if history_is_valid:
        log.info("history_summary", chars=len(history_result))
        log.debug("history_summary full", history_summary=history_result)

    kb_summary = None
    kb_project_ids: list[str] = []
    if isinstance(kb_result, KBAgentOutput):
        if len(kb_result.projects) == 0:
            kb_summary = "未匹配到任何项目。"
        else:
            parts = []
            for p in kb_result.projects:
                kb_project_ids.append(p.project_id)
                project_parts = [f"匹配项目: {p.project_name} (ID: {p.project_id})"]
                targeting_lines = [f"- 置信度: {p.match_confidence}"]
                if p.source_categories:
                    targeting_lines.append(f"- 命中文档类型: {', '.join(p.source_categories)}")
                if p.service_keywords:
                    targeting_lines.append(f"- 候选服务关键词: {', '.join(p.service_keywords)}")
                if p.server_keywords:
                    targeting_lines.append(f"- 候选服务器关键词: {', '.join(p.server_keywords)}")
                if p.entrypoint_hints:
                    targeting_lines.append(f"- 入口线索: {', '.join(p.entrypoint_hints)}")
                if len(targeting_lines) > 1:
                    project_parts.append("### 目标锁定提示\n" + "\n".join(targeting_lines))
                if p.agents_md_content and not p.agents_md_empty:
                    project_parts.append(f"### AGENTS.md\n{p.agents_md_content}")
                elif p.agents_md_empty:
                    project_parts.append("### AGENTS.md\n[空 - 未配置服务信息]")
                if p.business_context:
                    project_parts.append(f"### 业务背景\n{p.business_context}")
                parts.append("\n\n".join(project_parts))

            kb_summary = "\n\n---\n\n".join(parts)
            # If any project has empty agents_md, append hint
            if any(p.agents_md_empty for p in kb_result.projects):
                kb_summary += "\n\n[需要补充]"
    elif isinstance(kb_result, str):
        kb_summary = kb_result

    if kb_summary:
        log.info("kb_summary", chars=len(kb_summary), project_ids=kb_project_ids)
        log.debug("kb_summary full", kb_summary=kb_summary)

    log.info("===== Gathering context completed =====")

    return {
        "incident_history_summary": history_result if history_is_valid else None,
        "kb_summary": kb_summary,
        "kb_project_ids": kb_project_ids,
    }
