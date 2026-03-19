import asyncio
import json
import uuid

import orjson
import redis.asyncio as aioredis
from langchain_core.messages import HumanMessage

from src.config import get_settings
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.graph import compile_graph
from src.ops_agent.state import OpsState
from src.ops_agent.tools.safety import CommandSafety, CommandType
from src.db.connection import get_session_factory
from src.db.models import Incident
from src.lib.logger import logger
from src.services.approval_service import ApprovalService
from src.services.notification_service import notify_fire_and_forget
from src.services.post_incident import run_post_incident_tasks


class AgentRunner:
    def __init__(self, publisher: EventPublisher, checkpointer=None, redis: aioredis.Redis | None = None):
        self.publisher = publisher
        self.redis = redis
        self.graph = compile_graph(checkpointer=checkpointer)
        # Streaming answer state
        self._answer_stream_active = False
        self._answer_args_buffer = ""
        self._answer_published_len = 0
        self._thinking_done_sent = False
        # Streaming ask_human state
        self._ask_human_stream_active = False
        self._ask_human_args_buffer = ""
        self._ask_human_published_len = 0
        self._ask_human_streamed = False

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
    ) -> str:
        self._reset_answer_stream_state()
        self._ask_human_streamed = False
        self._reset_ask_human_stream_state()
        sid = incident_id[:8]
        thread_id = str(uuid.uuid4())
        channel = EventPublisher.channel_for_incident(incident_id)

        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": get_settings().agent_recursion_limit}

        initial_state = {
            "messages": [HumanMessage(content=f"事件描述: {description}")],
            "incident_id": incident_id,
            "description": description,
            "severity": severity,
            "is_complete": False,
            "needs_approval": False,
            "pending_tool_call": None,
            "approval_decision": None,
            "ask_human_count": 0,
            "incident_history_summary": None,
            "kb_summary": None,
            "kb_project_id": None,
        }

        logger.info(f"\n[{sid}] [main] ===== Agent lifecycle started =====")
        logger.info(f"[{sid}] [main] thread_id={thread_id}, severity={severity}, recursion_limit={config['recursion_limit']}")

        cancelled = False
        try:
            async for event in self.graph.astream_events(initial_state, config=config, version="v2"):
                cancel_reason = await self._check_cancelled(incident_id)
                if cancel_reason:
                    logger.info(f"[{sid}] [main] Agent cancelled: {cancel_reason}")
                    cancelled = True
                    break
                await self._process_event(channel, event)
        except Exception as e:
            logger.error(f"[{sid}] [main] Agent error: {e}")
            await self.publisher.publish(channel, "error", {"message": str(e)})
            raise

        await self.publisher.flush_remaining(channel)
        if not cancelled:
            await self._post_run(config, channel, incident_id)
        logger.info(f"\n[{sid}] [main] ===== Agent lifecycle completed =====")
        return thread_id

    async def resume_with_human_input(self, thread_id: str, incident_id: str, human_input: str) -> None:
        """Resume graph from ask_human interrupt with user's response."""
        self._reset_answer_stream_state()
        self._ask_human_streamed = False
        self._reset_ask_human_stream_state()
        channel = EventPublisher.channel_for_incident(incident_id)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": get_settings().agent_recursion_limit}

        sid = incident_id[:8]

        # Resume from ask_human or confirm_resolution interrupt
        state = await self.graph.aget_state(config)
        next_nodes = state.next or ()
        if "ask_human" not in next_nodes and "confirm_resolution" not in next_nodes:
            return

        from langgraph.types import Command

        resume_input = Command(resume=human_input)

        logger.info(f"[{sid}] [main] Resuming agent (human input), thread={thread_id}")
        logger.debug(f"[{sid}] [main] human_input: {human_input[:200]}")

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
        self._reset_answer_stream_state()
        self._ask_human_streamed = False
        self._reset_ask_human_stream_state()
        sid = incident_id[:8]
        channel = EventPublisher.channel_for_incident(incident_id)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": get_settings().agent_recursion_limit}

        logger.info(f"[{sid}] [main] Resuming agent (approval), thread={thread_id}, decision={approval_result.get('decision')}")

        from langgraph.types import Command

        decision = approval_result.get("decision", "approved")
        resume_input = Command(resume=None, update={"approval_decision": decision})

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
            logger.error(f"Agent resume error for incident {incident_id}: {e}")
            await self.publisher.publish(channel, "error", {"message": str(e)})
            raise

        await self.publisher.flush_remaining(channel)
        if not cancelled:
            await self._post_run(config, channel, incident_id)

    async def _post_run(self, config: dict, channel: str, incident_id: str) -> None:
        sid = incident_id[:8]
        state = await self.graph.aget_state(config)
        vals = state.values

        logger.info(f"[{sid}] [post_run] Post-run: next_nodes={state.next}, is_complete={vals.get('is_complete')}")

        # Interrupted before human_approval → create approval record + SSE
        if "human_approval" in (state.next or ()):
            pending = self._extract_pending_tool_call(vals)
            if pending:
                args = pending.get("args", {})
                # Derive risk_level from CommandSafety instead of LLM args
                command = args.get("command", "")
                cmd_type = CommandSafety.classify(command)
                risk_level = "HIGH" if cmd_type == CommandType.DANGEROUS else "MEDIUM"
                logger.info(f"[{sid}] [post_run] human_approval interrupt: tool={pending['name']}, cmd_type={cmd_type.name}, risk={risk_level}")
                logger.debug(f"[{sid}] [post_run] approval command: {command[:200]}")
                async with get_session_factory()() as session:
                    approval = await ApprovalService(session).create(
                        incident_id=uuid.UUID(incident_id),
                        tool_name=pending["name"],
                        tool_args=orjson.dumps(args).decode(),
                        risk_level=risk_level,
                        explanation=args.get("explanation"),
                    )
                logger.info(f"[{sid}] [post_run] Approval created: id={approval.id}")
                await self.publisher.publish(channel, "approval_required", {
                    "approval_id": str(approval.id),
                    "tool_name": pending["name"],
                    "tool_args": {**args, "risk_level": risk_level},
                })
                notify_fire_and_forget(
                    "need_approval", incident_id,
                    vals.get("description", "")[:80],
                    severity=vals.get("severity", ""),
                    command=command,
                    risk_level=risk_level,
                    explanation=args.get("explanation", ""),
                )

        # Interrupted before ask_human → extract question and publish SSE
        if "ask_human" in (state.next or ()):
            question = self._extract_ask_human_question(vals)
            if question:
                logger.info(f"[{sid}] [post_run] ask_human interrupt: question={question[:100]}, streamed={self._ask_human_streamed}")
                if not self._ask_human_streamed:
                    # Non-streamed (implicit ask_human): publish full question + done
                    await self.publisher.publish(channel, "ask_human", {
                        "question": question,
                    })
                    await self.publisher.publish(channel, "ask_human_done", {})
                notify_fire_and_forget(
                    "ask_human", incident_id,
                    vals.get("description", "")[:80],
                    severity=vals.get("severity", ""),
                    question=question,
                )

        # Interrupted before confirm_resolution → publish confirm event
        if "confirm_resolution" in (state.next or ()):
            logger.info(f"[{sid}] [post_run] confirm_resolution interrupt")
            await self.publisher.publish(channel, "confirm_resolution_required", {})

        # Graph complete → update DB, send done SSE, fire background tasks
        if vals.get("is_complete"):
            # ① DB: status → resolved
            async with get_session_factory()() as session:
                incident = await session.get(Incident, uuid.UUID(incident_id))
                if incident and incident.status == "investigating":
                    incident.status = "resolved"
                    await session.commit()
                    logger.info(f"[{sid}] [post_run] status -> resolved")

            # ② SSE: done (immediately, no waiting for LLM)
            await self.publisher.publish(channel, "done", {})

            # ③ Background: all post-incident work (summary, title, history, knowledge extraction)
            asyncio.create_task(run_post_incident_tasks(
                incident_id,
                kb_project_id=vals.get("kb_project_id"),
            ))

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

    def _reset_answer_stream_state(self) -> None:
        self._answer_stream_active = False
        self._answer_args_buffer = ""
        self._answer_published_len = 0
        self._thinking_done_sent = False

    def _reset_ask_human_stream_state(self) -> None:
        self._ask_human_stream_active = False
        self._ask_human_args_buffer = ""
        self._ask_human_published_len = 0

    def _extract_answer_delta(self) -> str | None:
        for suffix in ['"}', '" }']:
            try:
                parsed = json.loads(self._answer_args_buffer + suffix)
                content = parsed.get("answer_md", "")
                delta = content[self._answer_published_len:]
                self._answer_published_len = len(content)
                return delta if delta else None
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    def _extract_ask_human_delta(self) -> str | None:
        """Same as _extract_answer_delta but extracts the question field."""
        for suffix in ['"}', '" }']:
            try:
                parsed = json.loads(self._ask_human_args_buffer + suffix)
                content = parsed.get("question", "")
                delta = content[self._ask_human_published_len:]
                self._ask_human_published_len = len(content)
                return delta if delta else None
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    def _get_phase_agent(self, event: dict) -> tuple[str, str]:
        """Extract phase and agent from event metadata."""
        metadata = event.get("metadata", {})
        node = metadata.get("langgraph_node", "")
        if node == "gather_context":
            return "gather_context", "history"
        return "investigation", ""

    async def _process_event(self, channel: str, event: dict) -> None:
        kind = event.get("event")
        metadata = event.get("metadata", {})
        node = metadata.get("langgraph_node", "")

        # Extract incident_id short prefix from channel
        # channel format: "incident:<uuid>"
        sid = channel.split(":")[-1][:8] if ":" in channel else ""

        # 子 agent 通过自己的 callback 发布事件，跳过避免重复
        if node in ("gather_context", "confirm_resolution"):
            return

        phase, agent = self._get_phase_agent(event)

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if not chunk:
                return

            # Check for tool_call_chunks (streaming tool calls)
            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tcc in chunk.tool_call_chunks:
                    if tcc.get("name") == "complete":
                        self._answer_stream_active = True
                        self._answer_args_buffer = ""
                        self._answer_published_len = 0
                        # End thinking stream
                        if not self._thinking_done_sent:
                            await self.publisher.publish(channel, "thinking_done", {
                                "phase": phase, "agent": agent,
                            })
                            self._thinking_done_sent = True

                    if tcc.get("name") == "ask_human":
                        self._ask_human_stream_active = True
                        self._ask_human_args_buffer = ""
                        self._ask_human_published_len = 0
                        self._ask_human_streamed = True
                        if not self._thinking_done_sent:
                            await self.publisher.publish(channel, "thinking_done", {
                                "phase": phase, "agent": agent,
                            })
                            self._thinking_done_sent = True

                    if self._answer_stream_active and tcc.get("args"):
                        self._answer_args_buffer += tcc["args"]
                        delta = self._extract_answer_delta()
                        if delta:
                            await self.publisher.publish(channel, "answer", {
                                "content": delta, "phase": phase,
                            })

                    if self._ask_human_stream_active and tcc.get("args"):
                        self._ask_human_args_buffer += tcc["args"]
                        delta = self._extract_ask_human_delta()
                        if delta:
                            await self.publisher.publish(channel, "ask_human", {
                                "question": delta,
                            })

            # Regular content (thinking) — only if not in answer/ask_human stream
            if chunk.content and not self._answer_stream_active and not self._ask_human_stream_active:
                await self.publisher.publish(channel, "thinking", {
                    "content": chunk.content,
                    "phase": phase,
                    "agent": agent,
                })

        elif kind == "on_chat_model_end":
            output = event["data"].get("output")
            if not output:
                return

            # Log full LLM response
            content_text = output.content if hasattr(output, "content") else ""
            tool_calls = output.tool_calls if hasattr(output, "tool_calls") else []
            logger.info(f"\n[{sid}] [main] LLM response: content_len={len(content_text)}, tool_calls={len(tool_calls)}")
            if content_text:
                logger.info(f"\n[{sid}] [main] LLM content:\n{content_text}\n")
            for tc in tool_calls:
                logger.info(f"\n[{sid}] [main] LLM tool_call: {tc['name']}({tc.get('args', {})})")

            if self._answer_stream_active:
                # Already streamed answer via tool_call_chunks, just send answer_done
                await self.publisher.publish(channel, "answer_done", {"phase": phase})
                self._reset_answer_stream_state()
            elif self._ask_human_stream_active:
                await self.publisher.publish(channel, "ask_human_done", {})
                self._reset_ask_human_stream_state()
            else:
                # End current thinking segment
                await self.publisher.publish(channel, "thinking_done", {
                    "phase": phase, "agent": agent,
                })
                # Fallback: check for complete tool call → publish answer in one shot
                if hasattr(output, "tool_calls") and output.tool_calls:
                    for tc in output.tool_calls:
                        if tc["name"] == "complete":
                            answer_md = tc["args"].get("answer_md", "")
                            if answer_md:
                                await self.publisher.publish(channel, "answer", {
                                    "content": answer_md, "phase": phase,
                                })
                                await self.publisher.publish(channel, "answer_done", {"phase": phase})
                            break

        elif kind == "on_tool_start":
            name = event.get("name", "")
            if name == "read_skill":
                return  # Don't emit tool_call; wait for tool_end to emit skill_read
            logger.info(f"\n[{sid}] [main] Tool start: {name}")
            logger.debug(f"[{sid}] [main] Tool input: {event['data'].get('input', {})}")
            await self.publisher.publish(channel, "tool_call", {
                "name": name,
                "args": event["data"].get("input", {}),
                "phase": phase,
                "agent": agent,
            })

        elif kind == "on_tool_end":
            name = event.get("name", "")
            if name == "read_skill":
                args = event["data"].get("input", {})
                output = str(event["data"].get("output", ""))
                success = not output.startswith("未找到")
                path = args.get("path", "")
                # Extract slug and determine display name
                parts = path.split("/", 1)
                skill_slug = parts[0]
                file_path = parts[1] if len(parts) > 1 else None
                skill_name = file_path or skill_slug
                await self.publisher.publish(channel, "skill_read", {
                    "skill_slug": skill_slug,
                    "skill_name": skill_name,
                    "content": output,
                    "success": success,
                    "phase": phase,
                    "agent": agent,
                })
                return
            output_str = str(event["data"].get("output", ""))
            logger.info(f"\n[{sid}] [main] Tool end: {name}")
            logger.debug(f"[{sid}] [main] Tool output: {output_str[:500]}")
            await self.publisher.publish(channel, "tool_result", {
                "name": name,
                "output": output_str,
                "phase": phase,
                "agent": agent,
            })
