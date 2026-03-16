import uuid

import orjson

from src.ops_agent.connectors.k8s import K8sConnector
from src.ops_agent.connectors.ssh import SSHConnector
from src.ops_agent.tools.safety import CommandSafety, CommandType

# Registry of connectors by connection ID
_connector_registry: dict[str, SSHConnector | K8sConnector] = {}


def register_connector(connection_id: str, connector: SSHConnector | K8sConnector):
    _connector_registry[connection_id] = connector


async def get_connector(connection_id: str) -> SSHConnector | K8sConnector:
    # 1. Check registry cache
    if connection_id in _connector_registry:
        return _connector_registry[connection_id]

    # 2. Cache miss → query DB → create connector by type → cache
    from src.config import get_settings
    from src.db.connection import get_session_factory
    from src.db.models import Connection
    from src.services.crypto import CryptoService

    factory = get_session_factory()
    async with factory() as session:
        conn = await session.get(Connection, uuid.UUID(connection_id))
        if not conn:
            raise ValueError(f"Connection not found: {connection_id}")

        crypto = CryptoService(key=get_settings().encryption_key)

        if conn.type == "kubernetes":
            if not conn.conn_config:
                raise ValueError(f"K8s connection missing conn_config: {connection_id}")
            config = orjson.loads(crypto.decrypt(conn.conn_config))
            connector = K8sConnector(
                kubeconfig=config["kubeconfig"],
                context=config.get("context"),
                namespace=config.get("namespace", "default"),
            )
        elif conn.type == "ssh":
            password = crypto.decrypt(conn.encrypted_password) if conn.encrypted_password else None
            private_key = (
                crypto.decrypt(conn.encrypted_private_key) if conn.encrypted_private_key else None
            )
            connector = SSHConnector(
                host=conn.host,
                port=conn.port,
                username=conn.username,
                password=password,
                private_key=private_key,
            )
        else:
            raise ValueError(f"Unsupported connection type for exec tools: {conn.type}")

        _connector_registry[connection_id] = connector
        return connector


async def list_connections(project_id: str = "") -> list[dict]:
    """List available project-scoped connections, excluding offline ones."""
    from sqlalchemy import select

    from src.db.connection import get_session_factory
    from src.db.models import Connection

    if not project_id:
        return []

    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Connection).where(Connection.status != "offline")
        stmt = stmt.where(Connection.project_id == uuid.UUID(project_id))

        result = await session.execute(stmt)
        conns = result.scalars().all()

        return [
            {
                "id": str(conn.id),
                "name": conn.name,
                "type": conn.type,
                "host": conn.host,
                "status": conn.status,
                "project_id": str(conn.project_id) if conn.project_id else "",
            }
            for conn in conns
        ]


async def exec_read(connection_id: str, command: str) -> dict:
    cmd_type = CommandSafety.classify(command)

    if cmd_type == CommandType.BLOCKED:
        return {"error": "Command blocked: this command is too dangerous to execute"}

    if cmd_type == CommandType.WRITE:
        return {"error": "This is a write command. Use exec_write instead, which requires approval."}

    connector = await get_connector(connection_id)
    result = await connector.execute(command)

    return {
        "exit_code": result.exit_code,
        "stdout": CommandSafety.compress_output(result.stdout),
        "stderr": result.stderr,
        "error": None,
    }


async def exec_write(connection_id: str, command: str) -> dict:
    cmd_type = CommandSafety.classify(command)

    if cmd_type == CommandType.BLOCKED:
        return {"error": "Command blocked: this command is too dangerous to execute"}

    connector = await get_connector(connection_id)
    result = await connector.execute(command)

    return {
        "exit_code": result.exit_code,
        "stdout": CommandSafety.compress_output(result.stdout),
        "stderr": result.stderr,
        "error": None,
    }
