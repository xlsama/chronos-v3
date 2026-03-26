import asyncio
import re

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult, format_as_table

log = get_logger(component="service_exec")


class HiveConnector(ServiceConnector):
    service_type = "hive"

    def __init__(self, host: str, port: int, username: str, password: str | None, database: str):
        self._host = host
        self._port = port
        self._username = username
        self._password = password or ""
        self._database = database
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            from pyhive import hive

            log.info("Connecting", host=self._host, port=self._port, database=self._database)
            self._conn = hive.connect(
                host=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                database=self._database,
                auth="CUSTOM",
            )
        return self._conn

    def _execute_sync(self, command: str) -> ServiceResult:
        try:
            conn = self._get_conn()
            cmd = command.strip()
            upper = cmd.upper()

            is_query = bool(re.match(r"^(SELECT|SHOW|EXPLAIN|DESCRIBE|DESC|WITH\s)", upper))
            log.info("Executing", mode="query" if is_query else "statement", command_len=len(cmd))
            log.debug("Executing", command=cmd)

            cursor = conn.cursor()
            try:
                cursor.execute(cmd)
                if is_query:
                    rows = cursor.fetchall()
                    columns = [d[0] for d in cursor.description] if cursor.description else []
                    output = format_as_table(columns, rows)
                    log.info("Query returned", row_count=len(rows))
                    return ServiceResult(success=True, output=output, row_count=len(rows))
                else:
                    log.info("Statement executed")
                    return ServiceResult(success=True, output="执行成功")
            finally:
                cursor.close()
        except Exception as e:
            log.error("Execute failed", error=str(e))
            return ServiceResult(success=False, output="", error=f"{type(e).__name__}: {e}")

    async def execute(self, command: str) -> ServiceResult:
        return await asyncio.to_thread(self._execute_sync, command)

    async def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
