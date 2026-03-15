import uuid

from langchain_core.messages import HumanMessage

from src.agent.event_publisher import EventPublisher
from src.agent.graph import compile_graph
from src.agent.state import OpsState
from src.lib.logger import logger


class AgentRunner:
    def __init__(self, publisher: EventPublisher, checkpointer=None):
        self.publisher = publisher
        self.graph = compile_graph(checkpointer=checkpointer)

    async def start(
        self,
        incident_id: str,
        title: str,
        description: str,
        severity: str,
        infrastructure_id: str,
        project_id: str = "",
    ) -> str:
        thread_id = str(uuid.uuid4())
        channel = EventPublisher.channel_for_incident(incident_id)

        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "messages": [HumanMessage(content=f"事件: {title}\n\n{description}")],
            "incident_id": incident_id,
            "infrastructure_id": infrastructure_id,
            "project_id": project_id,
            "title": title,
            "description": description,
            "severity": severity,
            "is_complete": False,
            "needs_approval": False,
            "pending_tool_call": None,
            "summary_md": None,
        }

        logger.info(f"Starting agent for incident {incident_id}, thread {thread_id}")

        try:
            async for event in self.graph.astream_events(initial_state, config=config, version="v2"):
                await self._process_event(channel, event)
        except Exception as e:
            logger.error(f"Agent error for incident {incident_id}: {e}")
            await self.publisher.publish(channel, "error", {"message": str(e)})
            raise

        return thread_id

    async def resume(self, thread_id: str, incident_id: str, approval_result: dict) -> None:
        channel = EventPublisher.channel_for_incident(incident_id)
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(f"Resuming agent for incident {incident_id}, thread {thread_id}")

        try:
            async for event in self.graph.astream_events(None, config=config, version="v2"):
                await self._process_event(channel, event)
        except Exception as e:
            logger.error(f"Agent resume error for incident {incident_id}: {e}")
            await self.publisher.publish(channel, "error", {"message": str(e)})
            raise

    async def _process_event(self, channel: str, event: dict) -> None:
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                await self.publisher.publish(channel, "thinking", {"content": chunk.content})

        elif kind == "on_tool_start":
            await self.publisher.publish(channel, "tool_call", {
                "name": event.get("name", ""),
                "args": event["data"].get("input", {}),
            })

        elif kind == "on_tool_end":
            await self.publisher.publish(channel, "tool_result", {
                "name": event.get("name", ""),
                "output": str(event["data"].get("output", "")),
            })

        elif kind == "on_chain_end":
            output = event["data"].get("output", {})
            if isinstance(output, dict):
                if output.get("is_complete"):
                    await self.publisher.publish(channel, "summary", {
                        "summary_md": output.get("summary_md", ""),
                    })
                if output.get("needs_approval"):
                    await self.publisher.publish(channel, "approval_required", {
                        "pending_tool_call": output.get("pending_tool_call"),
                    })
