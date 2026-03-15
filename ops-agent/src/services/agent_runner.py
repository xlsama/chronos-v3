import uuid

import orjson
from langchain_core.messages import HumanMessage

from src.agent.event_publisher import EventPublisher
from src.agent.graph import compile_graph
from src.agent.state import OpsState
from src.db.connection import get_session_factory
from src.db.models import Incident
from src.lib.logger import logger
from src.services.approval_service import ApprovalService


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

        await self._post_run(config, channel, incident_id)
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

        await self._post_run(config, channel, incident_id)

    async def _post_run(self, config: dict, channel: str, incident_id: str) -> None:
        state = await self.graph.aget_state(config)
        vals = state.values

        # Gap A/B: interrupted before human_approval → create approval record + SSE
        if "human_approval" in (state.next or ()):
            pending = self._extract_pending_tool_call(vals)
            if pending:
                args = pending.get("args", {})
                async with get_session_factory()() as session:
                    approval = await ApprovalService(session).create(
                        incident_id=uuid.UUID(incident_id),
                        tool_name=pending["name"],
                        tool_args=orjson.dumps(args).decode(),
                        risk_level=args.get("risk_level"),
                        risk_detail=args.get("risk_detail"),
                        explanation=args.get("explanation"),
                    )
                await self.publisher.publish(channel, "approval_required", {
                    "approval_id": str(approval.id),
                    "tool_name": pending["name"],
                    "tool_args": args,
                })

        # Gap C: graph complete → update Incident status + publish summary
        if vals.get("is_complete"):
            async with get_session_factory()() as session:
                incident = await session.get(Incident, uuid.UUID(incident_id))
                if incident:
                    incident.summary_md = vals.get("summary_md")
                    incident.status = "resolved"
                    await session.commit()
            await self.publisher.publish(channel, "summary", {
                "summary_md": vals.get("summary_md", ""),
            })

    @staticmethod
    def _extract_pending_tool_call(vals: dict) -> dict | None:
        """Extract the exec_write_tool call from the last AI message."""
        messages = vals.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "exec_write_tool":
                        return tc
        return None

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
