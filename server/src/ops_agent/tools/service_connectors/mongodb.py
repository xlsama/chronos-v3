import json
import re

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult

log = get_logger(component="service_exec")

# Admin commands → fallback suggestions when permission denied (code 13)
_ADMIN_CMD_FALLBACKS: dict[str, str] = {
    "listdatabases": (
        "权限不足，无法执行 listDatabases（需要集群管理员权限）。\n"
        "降级方案：\n"
        '1. 在已知数据库上列出集合: {"listCollections": 1, "$db": "<数据库名>"}\n'
        '2. 查看数据库统计: {"dbStats": 1, "$db": "<数据库名>"}\n'
        '3. 查看当前用户权限: {"connectionStatus": 1}'
    ),
    "serverstatus": (
        "权限不足，无法执行 serverStatus（需要 clusterMonitor 角色）。\n"
        "降级方案：\n"
        '1. 查看数据库统计: {"dbStats": 1}\n'
        '2. 查看集合统计: {"collStats": "<集合名>"}\n'
        '3. 查看连接状态: {"connectionStatus": 1}'
    ),
    "replsetgetstatus": (
        "权限不足，无法执行 replSetGetStatus（需要 clusterMonitor 角色）。\n"
        "降级方案：\n"
        '1. 查看基本副本集信息: {"hello": 1}\n'
        '2. 验证连接可用性: {"ping": 1}'
    ),
    "currentop": (
        "权限不足，无法执行 currentOp。\n"
        "降级方案：\n"
        "1. 查看当前用户自己的操作: "
        '{"aggregate": 1, "pipeline": [{"$currentOp": {"ownOps": true}}], "cursor": {}}\n'
        '2. 查看连接状态: {"connectionStatus": 1}'
    ),
    "top": (
        "权限不足，无法执行 top（需要 clusterMonitor 角色）。\n"
        "降级方案：\n"
        '1. 查看集合统计: {"collStats": "<集合名>"}\n'
        '2. 查看数据库统计: {"dbStats": 1}'
    ),
}

_GENERIC_AUTH_FALLBACK = (
    "权限不足，当前用户没有执行此操作的权限。\n"
    "建议：\n"
    '1. 查看当前用户角色和权限: {"connectionStatus": 1}\n'
    '2. 尝试在指定数据库上操作，在命令中添加 "$db": "<数据库名>"\n'
    "3. 如果是集群管理命令，尝试使用数据库级别的替代命令"
)


class MongoDBConnector(ServiceConnector):
    service_type = "mongodb"

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        database: str,
        auth_source: str | None = None,
    ):
        self._database = database
        # Build connection URI
        if username and password:
            self._uri = f"mongodb://{username}:{password}@{host}:{port}"
            if auth_source:
                self._uri += f"?authSource={auth_source}"
        else:
            self._uri = f"mongodb://{host}:{port}"
        self._client: AsyncIOMotorClient | None = None

    def _get_client(self) -> AsyncIOMotorClient:
        if self._client is None:
            # Mask password in URI for logging
            safe_uri = (
                re.sub(r"://[^:]+:[^@]+@", "://***:***@", self._uri)
                if "@" in self._uri
                else self._uri
            )
            log.info("Creating client", uri=safe_uri)
            self._client = AsyncIOMotorClient(self._uri, serverSelectionTimeoutMS=5000)
        return self._client

    async def execute(self, command: str) -> ServiceResult:
        try:
            cmd_doc = json.loads(command.strip())
        except json.JSONDecodeError as e:
            return ServiceResult(success=False, output="", error=f"JSON 解析错误: {e}")
        if not isinstance(cmd_doc, dict) or not cmd_doc:
            return ServiceResult(success=False, output="", error="命令必须是非空 JSON 对象")

        # Allow agent to target a specific database via "$db" key
        target_db = cmd_doc.pop("$db", None) or self._database

        cmd_str = str(cmd_doc)
        log.info("Executing command", command_len=len(cmd_str), database=target_db)
        log.debug("Executing command", command=cmd_str)
        try:
            client = self._get_client()
            db = client[target_db]
            result = await db.command(cmd_doc)
            output = json.dumps(result, indent=2, default=str, ensure_ascii=False)
            log.info("Command result", output_len=len(output))
            return ServiceResult(success=True, output=output)
        except OperationFailure as e:
            log.warning("MongoDB OperationFailure", code=e.code, error=str(e))
            if e.code == 13:  # Unauthorized
                first_key = next(iter(cmd_doc), "").lower()
                hint = _ADMIN_CMD_FALLBACKS.get(first_key, _GENERIC_AUTH_FALLBACK)
                return ServiceResult(
                    success=False,
                    output="",
                    error=f"OperationFailure: {e}\n\n[降级提示] {hint}",
                )
            return ServiceResult(success=False, output="", error=f"OperationFailure: {e}")
        except Exception as e:
            log.error("Execute failed", error=str(e))
            return ServiceResult(success=False, output="", error=f"{type(e).__name__}: {e}")

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
