import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.state import OpsState
from src.ops_agent.sub_agents.history_agent import run_history_agent
from src.ops_agent.sub_agents.kb_agent import run_kb_agent
from src.lib.logger import logger
from src.lib.redis import get_redis

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


def _build_callback(channel: str, agent: str) -> EventCallback:
    """Build an event callback that publishes to Redis with phase/agent metadata."""
    if not channel:
        async def noop(event_type: str, data: dict) -> None:
            pass
        return noop

    redis = get_redis()
    publisher = EventPublisher(redis=redis)

    async def callback(event_type: str, data: dict) -> None:
        await publisher.publish(
            channel,
            event_type,
            {**data, "phase": "gather_context", "agent": agent},
        )

    return callback


async def _safe_run(coro_func, *args) -> str | None:
    """Run a coroutine and return None on failure instead of raising."""
    try:
        return await coro_func(*args)
    except Exception as e:
        logger.error(f"{coro_func.__name__} failed: {e}")
        return None


async def gather_context_node(state: OpsState) -> dict:
    """Run sub-agents to gather context before the main agent starts."""
    channel = state.get("_event_channel", "")
    title = state["title"]
    description = state["description"]
    project_id = state.get("project_id", "")

    history_cb = _build_callback(channel, agent="history")
    kb_cb = _build_callback(channel, agent="kb")

    # Build tasks list — always run history, run KB only if project_id is set
    tasks = [_safe_run(run_history_agent, title, description, project_id, history_cb)]
    if project_id:
        tasks.append(_safe_run(run_kb_agent, title, description, project_id, kb_cb))

    results = await asyncio.gather(*tasks)

    return {
        "incident_history_summary": results[0],
        "kb_summary": results[1] if len(results) > 1 else None,
    }
