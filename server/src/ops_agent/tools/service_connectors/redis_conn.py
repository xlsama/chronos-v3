import shlex

import redis.asyncio as aioredis

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult

log = get_logger(component="service_exec")


def _format_redis_result(result) -> str:
    """Format Redis result in redis-cli style."""
    if result is None:
        return "(nil)"
    if isinstance(result, bytes):
        return result.decode(errors="replace")
    if isinstance(result, int):
        return f"(integer) {result}"
    if isinstance(result, float):
        return str(result)
    if isinstance(result, list):
        if not result:
            return "(empty array)"
        lines = []
        for i, item in enumerate(result, 1):
            lines.append(f"{i}) {_format_redis_result(item)}")
        return "\n".join(lines)
    if isinstance(result, dict):
        lines = []
        for k, v in result.items():
            key_str = k.decode(errors="replace") if isinstance(k, bytes) else str(k)
            val_str = _format_redis_result(v)
            lines.append(f"{key_str}: {val_str}")
        return "\n".join(lines)
    return str(result)


class RedisConnector(ServiceConnector):
    service_type = "redis"

    def __init__(self, host: str, port: int, password: str | None, db: int = 0):
        self._host = host
        self._port = port
        self._password = password
        self._db = db
        self._client: aioredis.Redis | None = None

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            log.info("Creating client", host=self._host, port=self._port, db=self._db)
            self._client = aioredis.Redis(
                host=self._host,
                port=self._port,
                password=self._password,
                db=self._db,
                decode_responses=False,
            )
        return self._client

    async def execute(self, command: str) -> ServiceResult:
        client = self._get_client()
        parts = shlex.split(command.strip())
        if not parts:
            return ServiceResult(success=False, output="", error="空命令")

        log.info("Executing", command=parts[0], args=" ".join(parts[1:])[:200])
        result = await client.execute_command(*parts)
        output = _format_redis_result(result)
        log.info("Result", output_len=len(output))
        return ServiceResult(success=True, output=output)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
