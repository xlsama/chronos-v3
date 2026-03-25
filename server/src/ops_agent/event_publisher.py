import uuid
from datetime import datetime, timezone

import orjson
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.lib.logger import get_logger

log = get_logger()

# Map event_type to Message role
_EVENT_ROLE = {
    "thinking": "assistant",
    "thinking_done": "assistant",
    "answer": "assistant",
    "answer_done": "assistant",
    "tool_use": "assistant",
    "tool_result": "assistant",
    "skill_read": "assistant",
    "ask_human": "assistant",
    "ask_human_done": "assistant",
    "done": "system",
    "agent_status": "system",
    "approval_required": "system",
    "approval_decided": "system",
    "error": "system",
    "incident_stopped": "system",
    "agent_interrupted": "system",
    "confirm_resolution_required": "system",
    "resolution_confirmed": "system",
}


class EventPublisher:
    def __init__(self, redis: aioredis.Redis, session_factory: async_sessionmaker | None = None):
        self.redis = redis
        self.session_factory = session_factory
        self._thinking_buffer: dict[tuple[str, str, str], dict] = {}  # (channel, phase, agent) -> {content, phase, agent}
        self._answer_buffer: dict[str, dict] = {}  # channel -> {content, phase}
        self._ask_human_buffer: dict[str, dict] = {}  # channel -> {question}

    async def publish(self, channel: str, event_type: str, data: dict) -> None:
        ts = datetime.now(timezone.utc)
        phase = data.get("phase", "")
        agent = data.get("agent", "")

        if event_type == "thinking":
            # Accumulate thinking tokens, push SSE immediately but don't persist
            buf_key = (channel, phase, agent)
            buf = self._thinking_buffer.setdefault(
                buf_key, {"content": "", "phase": phase, "agent": agent}
            )
            buf["content"] += data.get("content", "")
            await self._publish_sse(channel, event_type, data, ts)
            return

        if event_type == "thinking_done":
            # Flush buffer → persist complete thinking + thinking_done marker + SSE
            await self._flush_thinking(channel, phase, agent, ts)
            await self._persist(channel, event_type, data, ts)
            await self._publish_sse(channel, event_type, data, ts)
            return

        if event_type == "answer":
            # Accumulate answer tokens, push SSE immediately but don't persist
            buf = self._answer_buffer.setdefault(channel, {"content": "", "phase": phase})
            buf["content"] += data.get("content", "")
            await self._publish_sse(channel, event_type, data, ts)
            return

        if event_type == "answer_done":
            # Flush answer buffer → persist complete answer + SSE
            await self._flush_answer(channel, ts)
            await self._publish_sse(channel, event_type, data, ts)
            return

        if event_type == "ask_human":
            # Accumulate ask_human tokens, push SSE immediately but don't persist
            buf = self._ask_human_buffer.setdefault(channel, {"question": ""})
            buf["question"] += data.get("question", "")
            await self._publish_sse(channel, event_type, data, ts)
            return

        if event_type == "ask_human_done":
            # Flush ask_human buffer → persist complete ask_human + SSE
            await self._flush_ask_human(channel, ts)
            await self._publish_sse(channel, event_type, data, ts)
            return

        # Non-thinking event: flush accumulated thinking as safety net, then persist
        await self._flush_thinking(channel, phase, agent, ts)
        await self._persist(channel, event_type, data, ts)
        await self._publish_sse(channel, event_type, data, ts)

    async def flush_remaining(self, channel: str) -> None:
        """Call when agent run ends to flush any remaining thinking/answer/ask_human buffers."""
        ts = datetime.now(timezone.utc)
        keys_to_flush = [k for k in self._thinking_buffer if k[0] == channel]
        for key in keys_to_flush:
            buf = self._thinking_buffer.pop(key, None)
            if buf and buf["content"]:
                await self._persist(channel, "thinking", buf, ts)
        await self._flush_answer(channel, ts)
        buf = self._ask_human_buffer.pop(channel, None)
        if buf and buf["question"]:
            await self._persist(channel, "ask_human", buf, ts)

    async def _flush_thinking(self, channel: str, phase: str = "", agent: str = "", ts: datetime | None = None) -> None:
        buf = self._thinking_buffer.pop((channel, phase, agent), None)
        if buf and buf["content"]:
            await self._persist(channel, "thinking", buf, ts or datetime.now(timezone.utc))

    async def _flush_answer(self, channel: str, ts: datetime | None = None) -> None:
        buf = self._answer_buffer.pop(channel, None)
        if buf and buf["content"]:
            await self._persist(channel, "answer", buf, ts or datetime.now(timezone.utc))

    async def _flush_ask_human(self, channel: str, ts: datetime | None = None) -> None:
        buf = self._ask_human_buffer.pop(channel, None)
        if buf and buf["question"]:
            await self._persist(channel, "ask_human", buf, ts or datetime.now(timezone.utc))

    async def _persist(self, channel: str, event_type: str, data: dict, ts: datetime) -> None:
        if not self.session_factory:
            return
        try:
            from src.db.models import Message

            incident_id = channel.split(":")[1]
            role = _EVENT_ROLE.get(event_type, "system")
            content = self._extract_content(event_type, data)
            metadata = self._extract_metadata(event_type, data)
            async with self.session_factory() as session:
                msg = Message(
                    id=uuid.uuid4(),
                    incident_id=uuid.UUID(incident_id),
                    role=role,
                    event_type=event_type,
                    content=content,
                    metadata_json=metadata if metadata else None,
                    created_at=ts,
                )
                session.add(msg)
                await session.commit()
        except Exception as e:
            log.error("Failed to persist event", event_type=event_type, error=str(e))

    async def _publish_sse(self, channel: str, event_type: str, data: dict, ts: datetime) -> None:
        payload = orjson.dumps({
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "data": data,
            "timestamp": ts.isoformat(),
        }).decode()

        await self.redis.publish(channel, payload)

    @staticmethod
    def _extract_content(event_type: str, data: dict) -> str:
        if event_type == "thinking":
            return data.get("content", "")
        if event_type == "thinking_done":
            return ""
        if event_type == "answer_done":
            return ""
        if event_type == "answer":
            return data.get("content", "")
        if event_type == "agent_status":
            return data.get("status", "")
        if event_type == "tool_use":
            return data.get("name", "")
        if event_type == "tool_result":
            return data.get("output", "")
        if event_type == "skill_read":
            return data.get("skill_slug", "")
        if event_type == "ask_human":
            return data.get("question", "")
        if event_type == "ask_human_done":
            return ""
        if event_type == "done":
            return ""
        if event_type == "error":
            return data.get("message", "")
        if event_type == "incident_stopped":
            return data.get("reason", "")
        if event_type == "confirm_resolution_required":
            return ""
        if event_type == "resolution_confirmed":
            return ""
        return ""

    @staticmethod
    def _extract_metadata(event_type: str, data: dict) -> dict | None:
        if event_type == "thinking":
            meta = {}
            if data.get("phase"):
                meta["phase"] = data["phase"]
            if data.get("agent"):
                meta["agent"] = data["agent"]
            return meta or None
        if event_type == "thinking_done":
            meta = {}
            if data.get("phase"):
                meta["phase"] = data["phase"]
            if data.get("agent"):
                meta["agent"] = data["agent"]
            return meta or None
        if event_type in ("answer", "answer_done"):
            meta = {}
            if data.get("phase"):
                meta["phase"] = data["phase"]
            return meta or None
        if event_type == "agent_status":
            return {
                "phase": data.get("phase", ""),
                "agent": data.get("agent", ""),
                "status": data.get("status", ""),
            }
        if event_type == "tool_use":
            return {
                "name": data.get("name", ""),
                "args": data.get("args", {}),
                "tool_call_id": data.get("tool_call_id", ""),
                "phase": data.get("phase", ""),
                "agent": data.get("agent", ""),
            }
        if event_type == "tool_result":
            meta = {
                "name": data.get("name", ""),
                "tool_call_id": data.get("tool_call_id", ""),
                "phase": data.get("phase", ""),
                "agent": data.get("agent", ""),
            }
            if data.get("sources"):
                meta["sources"] = data["sources"]
            return meta
        if event_type == "skill_read":
            return {
                "skill_slug": data.get("skill_slug", ""),
                "skill_name": data.get("skill_name", ""),
                "content": data.get("content", ""),
                "success": data.get("success", True),
            }
        if event_type == "approval_required":
            return {
                "approval_id": data.get("approval_id", ""),
                "tool_name": data.get("tool_name", ""),
                "tool_args": data.get("tool_args", {}),
            }
        if event_type == "approval_decided":
            return {
                "approval_id": data.get("approval_id", ""),
                "decision": data.get("decision", ""),
                "decided_by": data.get("decided_by", ""),
            }
        if event_type == "confirm_resolution_required":
            return None
        if event_type == "resolution_confirmed":
            return None
        return None

    @staticmethod
    def channel_for_incident(incident_id: str) -> str:
        return f"incident:{incident_id}"
