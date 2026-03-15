import redis.asyncio as aioredis

from src.config import get_settings


def get_redis():
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


__all__ = ["get_redis"]
