import asyncio
import json
import time
import uuid

import orjson
import redis.asyncio as aioredis
from langchain_core.messages import HumanMessage

from src.env import get_settings
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.graph import compile_graph
from src.ops_agent.state import OpsState
from src.ops_agent.tools.tool_permissions import ShellSafety, ServiceSafety, CommandType
from src.db.connection import get_session_factory
from src.db.models import Incident
from src.lib.logger import get_logger
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
        # Thinking content log buffer
        self._thinking_content_log_buffer = ""

    @staticmethod
    def _format_agent_error(exc: Exception) -> str:
        """Normalize runtime errors into user-readable messages."""
        if isinstance(exc, KeyError):
            missing = str(exc).strip("'\" ")
            if missing:
                return (
                    f"Agent 调用了未注册的工具 `{missing}`。"
                    "当前信息不足，无法继续排查，请补充具体故障现象、受影响服务和发生时间。"
                )
        return str(exc)

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
        log = get_logger(component="main", sid=sid)
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
            "tool_call_retry_count": 0,
            "incident_history_summary": None,
            "kb_summary": None,
            "kb_project_id": None,
        }

        log.info("===== Agent lifecycle started =====")
        log.info("Agent config", thread_id=thread_id, severity=severity, recursion_limit=config["recursion_limit"])

        cancelled = False
        try:
            async for event in self.graph.astream_events(initial_state, config=config, version="v2"):
                cancel_reason = await self._check_cancelled(incident_id)
                if cancel_reason:
                    log.info("Agent cancelled", reason=cancel_reason)
                    cancelled = True
                    break
                await self._process_event(channel, event)
        except Exception as e:
            log.error("Agent error", error=str(e))
            await self.publisher.publish(channel, "error", {"message": self._format_agent_error(e)})
            raise

        await self.publisher.flush_remaining(channel)
        if not cancelled:
            await self._post_run(config, channel, incident_id)
        log.info("===== Agent lifecycle completed =====")
        return thread_id

    async def resume_with_human_input(self, thread_id: str, incident_id: str, human_input: str) -> None:
        """Resume graph from ask_human interrupt with user's response."""
        self._reset_answer_stream_state()
        self._ask_human_streamed = False
        self._reset_ask_human_stream_state()
        channel = EventPublisher.channel_for_incident(incident_id)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": get_settings().agent_recursion_limit}

        sid = incident_id[:8]
        log = get_logger(component="main", sid=sid)

        state = await self.graph.aget_state(config)
        next_nodes = state.next or ()
        if "ask_human" not in next_nodes and "confirm_resolution" not in next_nodes:
            return

        from langgraph.types import Command

        resume_input = Command(resume=human_input)

        log.info("Resuming agent (human input)", thread_id=thread_id)
        log.debug("human_input", content=human_input[:200])

        cancelled = False
        try:
            async for event in self.graph.astream_events(resume_input, config=config, version="v2"):
                cancel_reason = await self._check_cancelled(incident_id)
                if cancel_reason:
                    get_logger(component="main").info("Agent cancelled", incident_id=incident_id, reason=cancel_reason)
                    cancelled = True
                    break
                await self._process_event(channel, event)
        except Exception as e:
            get_logger(component="main").error("Agent resume (human input) error", incident_id=incident_id, error=str(e))
            await self.publisher.publish(channel, "error", {"message": self._format_agent_error(e)})
            raise

        await self.publisher.flush_remaining(channel)
        if not cancelled:
            await self._post_run(config, channel, incident_id)

    async def resume(self, thread_id: str, incident_id: str, approval_result: dict) -> None:
        self._reset_answer_stream_state()
        self._ask_human_streamed = False
        self._reset_ask_human_stream_state()
        sid = incident_id[:8]
        log = get_logger(component="main", sid=sid)
        channel = EventPublisher.channel_for_incident(incident_id)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": get_settings().agent_recursion_limit}

        log.info("Resuming agent (approval)", thread_id=thread_id, decision=approval_result.get("decision"))

        from langgraph.types import Command

        decision = approval_result.get("decision", "approved")
        resume_input = Command(resume=None, update={"approval_decision": decision})

        cancelled = False
        try:
            async for event in self.graph.astream_events(resume_input, config=config, version="v2"):
                cancel_reason = await self._check_cancelled(incident_id)
                if cancel_reason:
                    get_logger(component="main").info("Agent cancelled", incident_id=incident_id, reason=cancel_reason)
                    cancelled = True
                    break
                await self._process_event(channel, event)
        except Exception as e:
            get_logger(component="main").error("Agent resume error", incident_id=incident_id, error=str(e))
            await self.publisher.publish(channel, "error", {"message": self._format_agent_error(e)})
            raise

        await self.publisher.flush_remaining(channel)
        if not cancelled:
            await self._post_run(config, channel, incident_id)

    async def _post_run(self, config: dict, channel: str, incident_id: str) -> None:
        sid = incident_id[:8]
        log = get_logger(component="post_run", sid=sid)
        state = await self.graph.aget_state(config)
        vals = state.values

        log.info("Post-run",
                 next_nodes=state.next,
                 is_complete=vals.get("is_complete"),
                 tool_call_retry_count=vals.get("tool_call_retry_count", 0),
                 ask_human_count=vals.get("ask_human_count", 0))

        if "human_approval" in (state.next or ()):
            pending = self._extract_pending_tool_call(vals)
            if pending:
                args = pending.get("args", {})
                tool_name = pending["name"]
                command = args.get("command", "")

                if tool_name in ("ssh_bash", "bash"):
                    cmd_type = ShellSafety.classify(command, local=(tool_name == "bash"))
                elif tool_name == "service_exec":
                    from src.ops_agent.nodes.main_agent import _get_service_type
                    service_type = await _get_service_type(args.get("service_id", ""))
                    cmd_type = ServiceSafety.classify(service_type, command)
                else:
                    cmd_type = CommandType.WRITE

                risk_level = "HIGH" if cmd_type == CommandType.DANGEROUS else "MEDIUM"
                log.info("human_approval interrupt", tool=tool_name, cmd_type=cmd_type.name, risk=risk_level)
                log.debug("approval command", command=command[:200])
                async with get_session_factory()() as session:
                    approval = await ApprovalService(session).create(
                        incident_id=uuid.UUID(incident_id),
                        tool_name=pending["name"],
                        tool_args=orjson.dumps(args).decode(),
                        risk_level=risk_level,
                        explanation=args.get("explanation"),
                    )
                log.info("Approval created", approval_id=str(approval.id))
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

        if "ask_human" in (state.next or ()):
            question = self._extract_ask_human_question(vals)
            if question:
                log.info("ask_human interrupt", question=question[:100], streamed=self._ask_human_streamed)
                if not self._ask_human_streamed:
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

        if "confirm_resolution" in (state.next or ()):
            log.info("confirm_resolution interrupt")
            await self.publisher.publish(channel, "confirm_resolution_required", {})

        if vals.get("is_complete"):
            async with get_session_factory()() as session:
                incident = await session.get(Incident, uuid.UUID(incident_id))
                if incident and incident.status == "investigating":
                    incident.status = "resolved"
                    await session.commit()
                    log.info("status -> resolved")

            await self.publisher.publish(channel, "done", {})

            asyncio.create_task(run_post_incident_tasks(
                incident_id,
                kb_project_id=vals.get("kb_project_id"),
            ))

    _APPROVAL_TOOLS = {"ssh_bash", "bash", "service_exec"}

    @staticmethod
    def _extract_pending_tool_call(vals: dict) -> dict | None:
        """Extract the tool call that needs approval from the last AI message."""
        messages = vals.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] in AgentRunner._APPROVAL_TOOLS:
                        return tc
        return None

    @staticmethod
    def _extract_ask_human_question(vals: dict) -> str | None:
        """Extract the question from the last AI message.

        Handles two cases:
        1. Explicit ask_human tool call -> extract question from args
        2. Plain text response (no tool calls) -> use message content as question
        """
        messages = vals.get("messages", [])
        for msg in reversed(messages):
            if not hasattr(msg, "tool_calls"):
                continue
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "ask_human":
                        return tc["args"].get("question", "")
            elif hasattr(msg, "content") and msg.content:
                return msg.content
        return None

    def _reset_answer_stream_state(self) -> None:
        self._answer_stream_active = False
        self._answer_args_buffer = ""
        self._answer_published_len = 0
        self._thinking_done_sent = False
        self._thinking_content_log_buffer = ""

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

        sid = channel.split(":")[-1][:8] if ":" in channel else ""
        stream_log = get_logger(component="stream", sid=sid)

        if node in ("gather_context", "confirm_resolution"):
            return

        phase, agent = self._get_phase_agent(event)

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if not chunk:
                return

            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tcc in chunk.tool_call_chunks:
                    if tcc.get("name") == "complete":
                        self._answer_stream_active = True
                        self._answer_args_buffer = ""
                        self._answer_published_len = 0
                        if not self._thinking_done_sent:
                            await self.publisher.publish(channel, "thinking_done", {
                                "phase": phase, "agent": agent,
                            })
                            self._thinking_done_sent = True
                        stream_log.info("Answer stream started", thinking_chars=len(self._thinking_content_log_buffer))

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
                        stream_log.info("Ask_human stream started", thinking_chars=len(self._thinking_content_log_buffer))

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

            if chunk.content and not self._answer_stream_active and not self._ask_human_stream_active:
                self._thinking_content_log_buffer += chunk.content
                await self.publisher.publish(channel, "thinking", {
                    "content": chunk.content,
                    "phase": phase,
                    "agent": agent,
                })

        elif kind == "on_chat_model_end":
            output = event["data"].get("output")
            if not output:
                return

            main_log = get_logger(component="main", sid=sid)
            content_text = output.content if hasattr(output, "content") else ""
            tool_calls = output.tool_calls if hasattr(output, "tool_calls") else []
            main_log.info("LLM response", content_len=len(content_text), tool_calls=len(tool_calls))
            if content_text:
                main_log.info("LLM content", content=content_text)
            for tc in tool_calls:
                main_log.info("LLM tool_call", name=tc["name"], args=tc.get("args", {}))

            if self._answer_stream_active:
                answer_len = self._answer_published_len
                stream_log.info("Answer stream done", answer_chars=answer_len)
                stream_log.debug("Answer content", content=self._answer_args_buffer)
                await self.publisher.publish(channel, "answer_done", {"phase": phase})
                self._reset_answer_stream_state()
            elif self._ask_human_stream_active:
                ask_human_len = self._ask_human_published_len
                stream_log.info("Ask_human stream done", question_chars=ask_human_len)
                await self.publisher.publish(channel, "ask_human_done", {})
                self._reset_ask_human_stream_state()
            else:
                thinking_len = len(self._thinking_content_log_buffer)
                stream_log.info("Thinking done (no tool_call)", thinking_chars=thinking_len)
                stream_log.debug("Thinking content", content=self._thinking_content_log_buffer)
                self._thinking_content_log_buffer = ""
                await self.publisher.publish(channel, "thinking_done", {
                    "phase": phase, "agent": agent,
                })
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
            skill_log = get_logger(component="skill", sid=sid)
            main_log = get_logger(component="main", sid=sid)
            if name == "read_skill":
                path = event["data"].get("input", {}).get("path", "")
                skill_log.info("read_skill start", path=path)
                return
            run_id = event.get("run_id", "")
            main_log.info("Tool start", tool=name)
            main_log.debug("Tool input", input=event["data"].get("input", {}))
            await self.publisher.publish(channel, "tool_call", {
                "name": name,
                "args": event["data"].get("input", {}),
                "tool_call_id": run_id,
                "phase": phase,
                "agent": agent,
            })

        elif kind == "on_tool_end":
            name = event.get("name", "")
            skill_log = get_logger(component="skill", sid=sid)
            main_log = get_logger(component="main", sid=sid)
            if name == "read_skill":
                args = event["data"].get("input", {})
                output = str(event["data"].get("output", ""))
                success = not output.startswith("未找到")
                path = args.get("path", "")
                skill_log.info("read_skill done", path=path, success=success, content_len=len(output))
                skill_log.debug("read_skill content", content=output)
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
            run_id = event.get("run_id", "")
            output_str = str(event["data"].get("output", ""))
            main_log.info("Tool end", tool=name)
            main_log.debug("Tool output", output=output_str[:500])
            await self.publisher.publish(channel, "tool_result", {
                "name": name,
                "output": output_str,
                "tool_call_id": run_id,
                "phase": phase,
                "agent": agent,
            })
