import json
import re

from motor.motor_asyncio import AsyncIOMotorClient

from src.lib.logger import logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult


class MongoDBConnector(ServiceConnector):
    service_type = "mongodb"

    def __init__(
        self, host: str, port: int, username: str | None, password: str | None, database: str
    ):
        self._database = database
        # Build connection URI
        if username and password:
            self._uri = f"mongodb://{username}:{password}@{host}:{port}"
        else:
            self._uri = f"mongodb://{host}:{port}"
        self._client: AsyncIOMotorClient | None = None

    def _get_client(self) -> AsyncIOMotorClient:
        if self._client is None:
            # Mask password in URI for logging
            safe_uri = re.sub(r"://[^:]+:[^@]+@", "://***:***@", self._uri) if "@" in self._uri else self._uri
            logger.info(f"[mongodb] Creating client: {safe_uri}")
            self._client = AsyncIOMotorClient(self._uri, serverSelectionTimeoutMS=5000)
        return self._client

    async def execute(self, command: str) -> ServiceResult:
        cmd_doc = json.loads(command.strip())
        if not isinstance(cmd_doc, dict) or not cmd_doc:
            return ServiceResult(success=False, output="", error="命令必须是非空 JSON 对象")

        logger.info(f"[mongodb] Executing command: {str(cmd_doc)[:200]}")
        client = self._get_client()
        db = client[self._database]
        result = await db.command(cmd_doc)
        output = json.dumps(result, indent=2, default=str, ensure_ascii=False)
        logger.info(f"[mongodb] Command result: {len(output)} chars")
        return ServiceResult(success=True, output=output)

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
