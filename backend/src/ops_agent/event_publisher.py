from datetime import datetime, timezone

import orjson
import redis.asyncio as aioredis

from src.lib.logger import logger


class EventPublisher:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def publish(self, channel: str, event_type: str, data: dict) -> None:
        payload = orjson.dumps({
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }).decode()

        await self.redis.publish(channel, payload)
        logger.debug(f"Published {event_type} to {channel}")

    @staticmethod
    def channel_for_incident(incident_id: str) -> str:
        return f"incident:{incident_id}"
