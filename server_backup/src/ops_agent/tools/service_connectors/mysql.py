import re

import aiomysql

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import (
    ServiceConnector,
    ServiceResult,
    format_as_table,
)

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
                autocommit=True,
                connect_timeout=5,
                pool_recycle=300,
            )
        return self._pool

    async def execute(self, command: str) -> ServiceResult:
        try:
            pool = await self._get_pool()
        except Exception as e:
            log.error("Connection failed", error=str(e))
            return ServiceResult(
                success=False, output="", error=f"连接失败: {type(e).__name__}: {e}"
            )

        try:
            cmd = command.strip()
            upper = cmd.upper()

            # 预检: 跨库引用检测
            from .sql_helpers import detect_cross_db_references

            cross_dbs = detect_cross_db_references(cmd, self._database)
            if cross_dbs:
                db_names = ", ".join(cross_dbs)
                return ServiceResult(
                    success=False,
                    output="",
                    error=(
                        f"检测到跨数据库引用: {db_names}。"
                        f"此连接绑定到数据库 '{self._database}'"
                        f"（{self._host}:{self._port}），"
                        f"无法通过 db.table 语法访问其他数据库（可能在不同服务器上）。"
                        f"请为每个数据库分别使用对应的 service_id 执行查询，然后合并结果。"
                    ),
                )

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
            from .sql_helpers import enhance_mysql_error

            enhanced = enhance_mysql_error(e, cmd, self._database)
            return ServiceResult(success=False, output="", error=enhanced)

    async def close(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
