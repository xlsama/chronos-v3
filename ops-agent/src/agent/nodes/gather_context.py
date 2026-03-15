from src.agent.event_publisher import EventPublisher
from src.agent.state import OpsState
from src.agent.sub_agents.history_agent import run_history_agent
from src.lib.logger import logger
from src.lib.redis import get_redis


async def gather_context_node(state: OpsState) -> dict:
    """Run sub-agents to gather context before the main agent starts."""
    channel = state.get("_event_channel", "")
    title = state["title"]
    description = state["description"]
    project_id = state.get("project_id", "")

    # Build event callback for real-time SSE streaming
    if channel:
        redis = get_redis()
        publisher = EventPublisher(redis=redis)

        async def event_callback(event_type: str, data: dict) -> None:
            await publisher.publish(
                channel,
                event_type,
                {**data, "phase": "gather_context", "agent": "history"},
            )
    else:
        async def event_callback(event_type: str, data: dict) -> None:
            pass

    # Run history sub agent
    try:
        history_summary = await run_history_agent(
            title=title,
            description=description,
            project_id=project_id,
            event_callback=event_callback,
        )
    except Exception as e:
        logger.error(f"History agent failed: {e}")
        history_summary = None

    return {"incident_history_summary": history_summary}
