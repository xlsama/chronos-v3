import re

import asyncpg

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import (
    ServiceConnector,
    ServiceResult,
    format_as_table,
)

log = get_logger(component="service_exec")


class PostgreSQLConnector(ServiceConnector):
    service_type = "postgresql"

    def __init__(self, host: str, port: int, username: str, password: str | None, database: str):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._database = database
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            log.info("Creating pool", host=self._host, port=self._port, database=self._database)
            self._pool = await asyncpg.create_pool(
                host=self._host,
                port=self._port,
                user=self._username,
                password=self._password,
                database=self._database,
                min_size=1,
                max_size=3,
            )
        return self._pool

    async def execute(self, command: str) -> ServiceResult:
        try:
            pool = await self._get_pool()
            cmd = command.strip()
            upper = cmd.upper()

            # Determine if this is a query (returns rows) or a statement
            is_query = bool(re.match(r"^(SELECT|SHOW|EXPLAIN|WITH\s)", upper))
            log.info("Executing", mode="query" if is_query else "statement", command_len=len(cmd))
            log.debug("Executing", command=cmd)

            async with pool.acquire() as conn:
                if is_query:
                    rows = await conn.fetch(cmd)
                    if not rows:
                        log.info("Query returned 0 rows")
                        return ServiceResult(success=True, output="(0 rows)", row_count=0)
                    columns = list(rows[0].keys())
                    data = [tuple(row.values()) for row in rows]
                    output = format_as_table(columns, data)
                    log.info("Query returned", row_count=len(data))
                    return ServiceResult(success=True, output=output, row_count=len(data))
                else:
                    result = await conn.execute(cmd)
                    log.info("Statement result", result=result)
                    return ServiceResult(success=True, output=f"执行成功: {result}")
        except Exception as e:
            log.error("Execute failed", error=str(e))
            from .sql_helpers import enhance_pg_error

            enhanced = enhance_pg_error(e, cmd, self._database)
            return ServiceResult(success=False, output="", error=enhanced)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
