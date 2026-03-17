import uuid
from datetime import datetime, timezone

import orjson
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.lib.logger import logger

# Map event_type to Message role
_EVENT_ROLE = {
    "thinking": "assistant",
    "tool_call": "assistant",
    "tool_result": "assistant",
    "skill_used": "assistant",
    "ask_human": "assistant",
    "summary": "assistant",
    "approval_required": "system",
    "approval_decided": "system",
    "error": "system",
    "incident_stopped": "system",
}

THINKING_FLUSH_THRESHOLD = 500


class EventPublisher:
    def __init__(self, redis: aioredis.Redis, session_factory: async_sessionmaker | None = None):
        self.redis = redis
        self.session_factory = session_factory
        self._thinking_buffer: dict[tuple[str, str, str], dict] = {}  # (channel, phase, agent) -> {content, phase, agent}

    async def publish(self, channel: str, event_type: str, data: dict) -> None:
        ts = datetime.now(timezone.utc)
        phase = data.get("phase", "")
        agent = data.get("agent", "")

        if event_type == "thinking":
            # Accumulate thinking tokens, don't persist yet, but still push SSE
            buf_key = (channel, phase, agent)
            buf = self._thinking_buffer.setdefault(
                buf_key, {"content": "", "phase": phase, "agent": agent}
            )
            buf["content"] += data.get("content", "")
            await self._publish_sse(channel, event_type, data, ts)
            # Auto-flush when buffer exceeds threshold to limit data loss window
            if len(buf["content"]) >= THINKING_FLUSH_THRESHOLD:
                await self._persist(channel, "thinking", buf, ts)
                buf["content"] = ""
            return

        # Non-thinking event: flush accumulated thinking for this (channel, phase, agent) first
        await self._flush_thinking(channel, phase, agent, ts)
        await self._persist(channel, event_type, data, ts)
        await self._publish_sse(channel, event_type, data, ts)

    async def flush_remaining(self, channel: str) -> None:
        """Call when agent run ends to flush any remaining thinking buffer."""
        ts = datetime.now(timezone.utc)
        keys_to_flush = [k for k in self._thinking_buffer if k[0] == channel]
        for key in keys_to_flush:
            buf = self._thinking_buffer.pop(key, None)
            if buf and buf["content"]:
                await self._persist(channel, "thinking", buf, ts)

    async def _flush_thinking(self, channel: str, phase: str = "", agent: str = "", ts: datetime | None = None) -> None:
        buf = self._thinking_buffer.pop((channel, phase, agent), None)
        if buf and buf["content"]:
            await self._persist(channel, "thinking", buf, ts or datetime.now(timezone.utc))

    async def _persist(self, channel: str, event_type: str, data: dict, ts: datetime) -> None:
        if not self.session_factory:
            return
        try:
            from src.db.models import Message

            incident_id = channel.split(":")[1]
            role = _EVENT_ROLE.get(event_type, "system")
            content = self._extract_content(event_type, data)
            metadata = self._extract_metadata(event_type, data)
            metadata_str = orjson.dumps(metadata).decode() if metadata else None

            async with self.session_factory() as session:
                msg = Message(
                    id=uuid.uuid4(),
                    incident_id=uuid.UUID(incident_id),
                    role=role,
                    event_type=event_type,
                    content=content,
                    metadata_json=metadata_str,
                    created_at=ts,
                )
                session.add(msg)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist event {event_type}: {e}")

    async def _publish_sse(self, channel: str, event_type: str, data: dict, ts: datetime) -> None:
        payload = orjson.dumps({
            "event_type": event_type,
            "data": data,
            "timestamp": ts.isoformat(),
        }).decode()

        await self.redis.publish(channel, payload)
        logger.debug(f"Published {event_type} to {channel}")

    @staticmethod
    def _extract_content(event_type: str, data: dict) -> str:
        if event_type == "thinking":
            return data.get("content", "")
        if event_type == "tool_call":
            return data.get("name", "")
        if event_type == "tool_result":
            return data.get("output", "")
        if event_type == "skill_used":
            return data.get("skill_name", "")
        if event_type == "ask_human":
            return data.get("question", "")
        if event_type == "summary":
            return data.get("summary_md", "")
        if event_type == "error":
            return data.get("message", "")
        if event_type == "incident_stopped":
            return data.get("reason", "")
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
        if event_type == "tool_call":
            return {
                "name": data.get("name", ""),
                "args": data.get("args", {}),
                "phase": data.get("phase", ""),
                "agent": data.get("agent", ""),
            }
        if event_type == "tool_result":
            meta = {
                "name": data.get("name", ""),
                "phase": data.get("phase", ""),
                "agent": data.get("agent", ""),
            }
            if data.get("sources"):
                meta["sources"] = data["sources"]
            return meta
        if event_type == "skill_used":
            return {
                "skill_name": data.get("skill_name", ""),
                "content": data.get("content", ""),
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
        return None

    @staticmethod
    def channel_for_incident(incident_id: str) -> str:
        return f"incident:{incident_id}"
