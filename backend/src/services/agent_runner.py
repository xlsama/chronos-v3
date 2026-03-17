import re
import uuid

import orjson
import redis.asyncio as aioredis
from langchain_core.messages import HumanMessage
from sqlalchemy import func, select

from src.config import get_settings
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.graph import compile_graph
from src.ops_agent.state import OpsState
from src.ops_agent.tools.safety import CommandSafety, CommandType
from src.db.connection import get_session_factory
from src.db.models import Incident, Message
from src.lib.logger import logger
from src.services.approval_service import ApprovalService
from src.services.incident_history_service import IncidentHistoryService
from src.services.notification_service import notify_fire_and_forget


def _has_root_cause(summary_md: str) -> bool:
    """Check if summary has a meaningful root cause analysis section."""
    match = re.search(r"##\s*根因分析\s*\n(.*?)(?=\n##|\Z)", summary_md, re.DOTALL)
    if not match:
        return False
    content = match.group(1).strip()
    if len(content) < 20:
        return False
    skip_patterns = ["暂无", "无法确定", "未能确定", "尚不明确"]
    return not any(p in content for p in skip_patterns)


class AgentRunner:
    def __init__(self, publisher: EventPublisher, checkpointer=None, redis: aioredis.Redis | None = None):
        self.publisher = publisher
        self.redis = redis
        self.graph = compile_graph(checkpointer=checkpointer)

    async def _check_cancelled(self, incident_id: str) -> str | None:
        """Check if this incident has been cancelled. Returns cancel reason or None."""
        if not self.redis:
            return None
        val = await self.redis.get(f"incident:{incident_id}:cancel")
        if val:
            return val.decode() if isinstance(val, bytes) else val
        return None

    async def start(
        self,
        incident_id: str,
        description: str,
        severity: str,
        project_id: str = "",
    ) -> str:
        thread_id = str(uuid.uuid4())
        channel = EventPublisher.channel_for_incident(incident_id)

        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": get_settings().agent_recursion_limit}
        logger.info(f"Agent config recursion_limit={config['recursion_limit']}")

        initial_state = {
            "messages": [HumanMessage(content=f"事件描述: {description}")],
            "incident_id": incident_id,
            "project_id": project_id,
            "description": description,
            "severity": severity,
            "is_complete": False,
            "needs_approval": False,
            "pending_tool_call": None,
            "summary_md": None,
            "incident_history_summary": None,
            "kb_summary": None,
            "_event_channel": channel,
        }

        logger.info(f"Starting agent for incident {incident_id}, thread {thread_id}")

        cancelled = False
        try:
            async for event in self.graph.astream_events(initial_state, config=config, version="v2"):
                cancel_reason = await self._check_cancelled(incident_id)
                if cancel_reason:
                    logger.info(f"Agent cancelled for incident {incident_id}: {cancel_reason}")
                    cancelled = True
                    break
                await self._process_event(channel, event)
        except Exception as e:
            logger.error(f"Agent error for incident {incident_id}: {e}")
            await self.publisher.publish(channel, "error", {"message": str(e)})
            raise

        await self.publisher.flush_remaining(channel)
        if not cancelled:
            await self._post_run(config, channel, incident_id)
        return thread_id

    async def resume_with_human_input(self, thread_id: str, incident_id: str, human_input: str) -> None:
        """Resume graph from ask_human interrupt with user's response."""
        channel = EventPublisher.channel_for_incident(incident_id)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": get_settings().agent_recursion_limit}

        # Only resume if graph is actually at ask_human interrupt
        state = await self.graph.aget_state(config)
        if "ask_human" not in (state.next or ()):
            return

        from langgraph.types import Command

        resume_input = Command(resume=human_input)

        logger.info(f"Resuming agent (human input) for incident {incident_id}, thread {thread_id}")

        cancelled = False
        try:
            async for event in self.graph.astream_events(resume_input, config=config, version="v2"):
                cancel_reason = await self._check_cancelled(incident_id)
                if cancel_reason:
                    logger.info(f"Agent cancelled for incident {incident_id}: {cancel_reason}")
                    cancelled = True
                    break
                await self._process_event(channel, event)
        except Exception as e:
            logger.error(f"Agent resume (human input) error for incident {incident_id}: {e}")
            await self.publisher.publish(channel, "error", {"message": str(e)})
            raise

        await self.publisher.flush_remaining(channel)
        if not cancelled:
            await self._post_run(config, channel, incident_id)

    async def resume(self, thread_id: str, incident_id: str, approval_result: dict) -> None:
        channel = EventPublisher.channel_for_incident(incident_id)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": get_settings().agent_recursion_limit}

        logger.info(f"Resuming agent for incident {incident_id}, thread {thread_id}")

        cancelled = False
        try:
            async for event in self.graph.astream_events(None, config=config, version="v2"):
                cancel_reason = await self._check_cancelled(incident_id)
                if cancel_reason:
                    logger.info(f"Agent cancelled for incident {incident_id}: {cancel_reason}")
                    cancelled = True
                    break
                await self._process_event(channel, event)
        except Exception as e:
            logger.error(f"Agent resume error for incident {incident_id}: {e}")
            await self.publisher.publish(channel, "error", {"message": str(e)})
            raise

        await self.publisher.flush_remaining(channel)
        if not cancelled:
            await self._post_run(config, channel, incident_id)

    async def _post_run(self, config: dict, channel: str, incident_id: str) -> None:
        state = await self.graph.aget_state(config)
        vals = state.values

        # Interrupted before human_approval → create approval record + SSE
        if "human_approval" in (state.next or ()):
            pending = self._extract_pending_tool_call(vals)
            if pending:
                args = pending.get("args", {})
                # Derive risk_level from CommandSafety instead of LLM args
                command = args.get("command", "")
                cmd_type = CommandSafety.classify(command)
                risk_level = "HIGH" if cmd_type == CommandType.DANGEROUS else "MEDIUM"
                async with get_session_factory()() as session:
                    approval = await ApprovalService(session).create(
                        incident_id=uuid.UUID(incident_id),
                        tool_name=pending["name"],
                        tool_args=orjson.dumps(args).decode(),
                        risk_level=risk_level,
                        explanation=args.get("explanation"),
                    )
                await self.publisher.publish(channel, "approval_required", {
                    "approval_id": str(approval.id),
                    "tool_name": pending["name"],
                    "tool_args": {**args, "risk_level": risk_level},
                })
                notify_fire_and_forget(
                    "need_approval", incident_id,
                    vals.get("description", "")[:80], detail=pending["name"],
                )

        # Interrupted before ask_human → extract question and publish SSE
        if "ask_human" in (state.next or ()):
            question = self._extract_ask_human_question(vals)
            if question:
                await self.publisher.publish(channel, "ask_human", {
                    "question": question,
                })
                notify_fire_and_forget(
                    "ask_human", incident_id,
                    vals.get("description", "")[:80], detail=question,
                )

        # Graph complete → update Incident status + publish summary (only if still investigating)
        if vals.get("is_complete"):
            summary_md = vals.get("summary_md", "")

            # Generate summary title (fast mini model, ~1s)
            summary_title = None
            if summary_md:
                try:
                    from src.services.incident_history_service import _generate_title
                    summary_title = await _generate_title(summary_md)
                except Exception as e:
                    logger.warning(f"Summary title generation failed for {incident_id}: {e}")

            async with get_session_factory()() as session:
                incident = await session.get(Incident, uuid.UUID(incident_id))
                if incident and incident.status == "investigating":
                    incident.summary_md = summary_md
                    incident.summary_title = summary_title
                    incident.status = "resolved"
                    await session.commit()

            await self.publisher.publish(channel, "summary", {
                "summary_md": summary_md,
                "summary_title": summary_title,
            })
            notify_fire_and_forget("resolved", incident_id, summary_title or vals.get("description", "")[:80])
            try:
                await self._auto_save_history(incident_id, summary_md)
            except Exception as e:
                logger.error(f"Auto-save history failed for {incident_id}: {e}")

    @staticmethod
    def _extract_pending_tool_call(vals: dict) -> dict | None:
        """Extract the bash tool call that needs approval from the last AI message."""
        messages = vals.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "bash":
                        return tc
        return None

    @staticmethod
    def _extract_ask_human_question(vals: dict) -> str | None:
        """Extract the question from the last AI message.

        Handles two cases:
        1. Explicit ask_human tool call → extract question from args
        2. Plain text response (no tool calls) → use message content as question
        """
        messages = vals.get("messages", [])
        for msg in reversed(messages):
            if not hasattr(msg, "tool_calls"):
                continue
            # Case 1: explicit ask_human tool call
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "ask_human":
                        return tc["args"].get("question", "")
            # Case 2: plain text response (routed to ask_human because no tool_calls)
            elif hasattr(msg, "content") and msg.content:
                return msg.content
        return None

    async def _auto_save_history(self, incident_id: str, summary_md: str) -> None:
        if not summary_md:
            return
        if not _has_root_cause(summary_md):
            logger.info(f"Auto-save skipped for {incident_id}: no valid root cause")
            return

        async with get_session_factory()() as session:
            # Check tool_call events with bash → agent executed commands
            tool_count = await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.incident_id == uuid.UUID(incident_id),
                    Message.event_type == "tool_call",
                    Message.content == "bash",
                )
            )
            if not tool_count:
                logger.info(f"Auto-save skipped for {incident_id}: no bash tool calls")
                return

            incident = await session.get(Incident, uuid.UUID(incident_id))
            if not incident or incident.saved_to_memory:
                return

            service = IncidentHistoryService(session=session)
            result = await service.auto_save(incident, summary_md)
            logger.info(f"Auto-save result for {incident_id}: {result}")

    def _get_phase_agent(self, event: dict) -> tuple[str, str]:
        """Extract phase and agent from event metadata."""
        metadata = event.get("metadata", {})
        node = metadata.get("langgraph_node", "")
        if node == "gather_context":
            return "gather_context", "history"
        if node == "summarize":
            return "summarize", ""
        return "main", ""

    async def _process_event(self, channel: str, event: dict) -> None:
        kind = event.get("event")
        metadata = event.get("metadata", {})
        node = metadata.get("langgraph_node", "")

        # 子 agent 通过自己的 callback 发布事件，跳过避免重复
        if node in ("gather_context", "summarize"):
            return

        phase, agent = self._get_phase_agent(event)

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                await self.publisher.publish(channel, "thinking", {
                    "content": chunk.content,
                    "phase": phase,
                    "agent": agent,
                })

        elif kind == "on_tool_start":
            name = event.get("name", "")
            if name == "use_skill":
                return  # Don't emit tool_call; wait for tool_end to emit skill_used
            await self.publisher.publish(channel, "tool_call", {
                "name": name,
                "args": event["data"].get("input", {}),
                "phase": phase,
                "agent": agent,
            })

        elif kind == "on_tool_end":
            name = event.get("name", "")
            if name == "use_skill":
                args = event["data"].get("input", {})
                output = str(event["data"].get("output", ""))
                await self.publisher.publish(channel, "skill_used", {
                    "skill_name": args.get("skill_name", ""),
                    "content": output,
                    "phase": phase,
                    "agent": agent,
                })
                return
            await self.publisher.publish(channel, "tool_result", {
                "name": name,
                "output": str(event["data"].get("output", "")),
                "phase": phase,
                "agent": agent,
            })
