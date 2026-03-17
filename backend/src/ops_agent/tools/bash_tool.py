import uuid

from src.ops_agent.ssh import SSHConnector
from src.ops_agent.tools.safety import CommandSafety, CommandType

# Registry of connectors by server ID
_connector_registry: dict[str, SSHConnector] = {}


def register_connector(server_id: str, connector: SSHConnector):
    _connector_registry[server_id] = connector


async def get_connector(server_id: str) -> SSHConnector:
    # 1. Check registry cache
    if server_id in _connector_registry:
        return _connector_registry[server_id]

    # 2. Cache miss → query DB → create connector → cache
    from src.config import get_settings
    from src.db.connection import get_session_factory
    from src.db.models import Server
    from src.services.server_service import ServerService
    from src.services.crypto import CryptoService

    factory = get_session_factory()
    async with factory() as session:
        try:
            server_uuid = uuid.UUID(server_id)
        except ValueError:
            raise ValueError(
                f"Invalid server_id '{server_id}': not a valid UUID. "
                f"Call list_servers() to get valid server IDs."
            )
        server = await session.get(Server, server_uuid)
        if not server:
            raise ValueError(f"Server not found: {server_id}")

        crypto = CryptoService(key=get_settings().encryption_key)
        service = ServerService(session=session, crypto=crypto)
        password, private_key = service.get_decrypted_credentials(server)
        bastion_password, bastion_private_key = service.get_decrypted_bastion_credentials(server)

        connector = SSHConnector(
            host=server.host,
            port=server.port,
            username=server.username,
            password=password,
            private_key=private_key,
            bastion_host=server.bastion_host,
            bastion_port=server.bastion_port,
            bastion_username=server.bastion_username,
            bastion_password=bastion_password,
            bastion_private_key=bastion_private_key,
        )

        _connector_registry[server_id] = connector
        return connector


async def list_servers(project_id: str = "") -> list[dict]:
    """List available servers, excluding offline ones. Optionally filter by project_id."""
    from sqlalchemy import select

    from src.db.connection import get_session_factory
    from src.db.models import Server, Project

    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Server).where(Server.status != "offline")
        if project_id:
            try:
                project = await session.get(Project, uuid.UUID(project_id))
                if project and project.linked_server_ids:
                    server_ids = [uuid.UUID(sid) for sid in project.linked_server_ids]
                    stmt = stmt.where(Server.id.in_(server_ids))
            except ValueError:
                pass  # invalid project_id, skip filter and return all

        result = await session.execute(stmt)
        servers = result.scalars().all()

        return [
            {
                "id": str(s.id),
                "name": s.name,
                "host": s.host,
                "status": s.status,
            }
            for s in servers
        ]


async def bash(server_id: str, command: str) -> dict:
    """Execute a shell command on the target server via SSH."""
    cmd_type = CommandSafety.classify(command)

    if cmd_type == CommandType.BLOCKED:
        return {"error": "命令被系统拦截：此命令过于危险，禁止执行"}

    # READ / WRITE / DANGEROUS all execute here
    # (WRITE/DANGEROUS have already been approved via route_decision → human_approval)
    try:
        connector = await get_connector(server_id)
    except ValueError as e:
        return {"error": str(e)}
    result = await connector.execute(command)

    return {
        "exit_code": result.exit_code,
        "stdout": CommandSafety.compress_output(result.stdout),
        "stderr": result.stderr,
        "error": None,
    }
