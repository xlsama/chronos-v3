from collections.abc import Callable, Coroutine
from typing import Any

from src.db.connection import get_session_factory
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.state import OpsState
from src.ops_agent.sub_agents.summarize_agent import run_summarize_agent
from src.lib.logger import logger
from src.lib.redis import get_redis

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


def _build_callback(channel: str) -> EventCallback:
    """Build an event callback that publishes to Redis with phase=summarize."""
    if not channel:
        async def noop(event_type: str, data: dict) -> None:
            pass
        return noop

    redis = get_redis()
    publisher = EventPublisher(redis=redis, session_factory=get_session_factory())

    async def callback(event_type: str, data: dict) -> None:
        await publisher.publish(
            channel,
            event_type,
            {**data, "phase": "summarize", "agent": "summarize"},
        )

    return callback


async def summarize_node(state: OpsState) -> dict:
    channel = state.get("_event_channel", "")
    callback = _build_callback(channel)

    try:
        summary_md = await run_summarize_agent(
            messages=state["messages"],
            description=state["description"],
            severity=state["severity"],
            event_callback=callback,
        )
    except Exception as e:
        logger.error(f"Summarize agent failed: {e}")
        summary_md = f"报告生成失败: {e}"

    return {
        "summary_md": summary_md,
        "is_complete": True,
    }
