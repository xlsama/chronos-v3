import re

import aiomysql

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult, format_as_table

log = get_logger(component="service_exec")


class MySQLConnector(ServiceConnector):
    service_type = "mysql"

    def __init__(self, host: str, port: int, username: str, password: str | None, database: str):
        self._host = host
        self._port = port
        self._username = username
        self._password = password or ""
        self._database = database
        self._pool: aiomysql.Pool | None = None

    async def _get_pool(self) -> aiomysql.Pool:
        if self._pool is None:
            log.info("Creating pool", host=self._host, port=self._port, database=self._database)
            self._pool = await aiomysql.create_pool(
                host=self._host,
                port=self._port,
                user=self._username,
                password=self._password,
                db=self._database,
                minsize=1,
                maxsize=3,
                charset="utf8mb4",
                autocommit=False,
            )
        return self._pool

    async def execute(self, command: str) -> ServiceResult:
        try:
            pool = await self._get_pool()
            cmd = command.strip()
            upper = cmd.upper()

            is_query = bool(re.match(r"^(SELECT|SHOW|EXPLAIN|DESCRIBE|DESC|WITH\s)", upper))
            log.info("Executing", mode="query" if is_query else "statement", command_len=len(cmd))
            log.debug("Executing", command=cmd)

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(cmd)
                    if is_query:
                        rows = await cur.fetchall()
                        columns = [d[0] for d in cur.description] if cur.description else []
                        output = format_as_table(columns, rows)
                        log.info("Query returned", row_count=len(rows))
                        return ServiceResult(success=True, output=output, row_count=len(rows))
                    else:
                        await conn.commit()
                        log.info("Statement affected", row_count=cur.rowcount)
                        return ServiceResult(
                            success=True,
                            output=f"执行成功: 影响 {cur.rowcount} 行",
                            row_count=cur.rowcount,
                        )
        except Exception as e:
            log.error("Execute failed", error=str(e))
            return ServiceResult(success=False, output="", error=f"{type(e).__name__}: {e}")

    async def close(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
