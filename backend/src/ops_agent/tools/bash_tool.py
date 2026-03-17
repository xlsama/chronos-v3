import asyncio
import time
import uuid

from src.lib.logger import logger
from src.ops_agent.ssh import SSHConnector
from src.ops_agent.tools.safety import CommandSafety, CommandType

# Registry of connectors by server ID with TTL and capacity management
_connector_registry: dict[str, tuple[SSHConnector, float]] = {}  # server_id -> (connector, last_used_time)
_registry_lock = asyncio.Lock()
_CONNECTOR_TTL = 600  # 10 minutes
_CONNECTOR_MAX_SIZE = 100


def _evict_expired() -> None:
    """Remove expired connectors from registry (must be called under lock)."""
    now = time.monotonic()
    expired = [k for k, (_, ts) in _connector_registry.items() if now - ts > _CONNECTOR_TTL]
    for k in expired:
        del _connector_registry[k]


async def invalidate_connector(server_id: str) -> None:
    """Remove a connector from cache, e.g. after credentials update."""
    async with _registry_lock:
        _connector_registry.pop(server_id, None)


def register_connector(server_id: str, connector: SSHConnector):
    _connector_registry[server_id] = (connector, time.monotonic())


async def get_connector(server_id: str) -> SSHConnector:
    async with _registry_lock:
        _evict_expired()

        # Check registry cache
        if server_id in _connector_registry:
            connector, _ = _connector_registry[server_id]
            _connector_registry[server_id] = (connector, time.monotonic())
            return connector

        # Enforce capacity limit
        if len(_connector_registry) >= _CONNECTOR_MAX_SIZE:
            oldest_key = min(_connector_registry, key=lambda k: _connector_registry[k][1])
            del _connector_registry[oldest_key]

    # Cache miss → query DB → create connector → cache
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

        async with _registry_lock:
            _connector_registry[server_id] = (connector, time.monotonic())
        return connector


async def list_servers(project_id: str = "") -> list[dict]:
    """List available servers, excluding offline ones. Optionally filter by project_id."""
    from sqlalchemy import select

    from src.db.connection import get_session_factory
    from src.db.models import Server, ProjectServer

    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Server).where(Server.status != "offline")
        if project_id:
            try:
                project_uuid = uuid.UUID(project_id)
                stmt = stmt.where(
                    Server.id.in_(
                        select(ProjectServer.server_id).where(ProjectServer.project_id == project_uuid)
                    )
                )
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

    logger.info(f"\n[bash_tool] Executing: server={server_id[:8]}..., cmd_type={cmd_type.name}, command={command[:100]}")

    if cmd_type == CommandType.BLOCKED:
        logger.warning(f"[bash_tool] BLOCKED: {command[:100]}")
        return {"error": "命令被系统拦截：此命令过于危险，禁止执行"}

    # READ / WRITE / DANGEROUS all execute here
    # (WRITE/DANGEROUS have already been approved via route_decision → human_approval)
    try:
        connector = await get_connector(server_id)
    except ValueError as e:
        logger.error(f"[bash_tool] Connection error: {e}")
        return {"error": str(e)}
    try:
        result = await connector.execute(command)
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning(f"[bash_tool] Timeout after {connector.timeout}s")
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"命令执行超时（{connector.timeout}秒）。如果是后台启动命令，进程可能已成功启动，请用 ps/pgrep 确认。",
            "error": None,
        }

    stdout_compressed = CommandSafety.compress_output(result.stdout)
    logger.info(f"[bash_tool] Result: exit_code={result.exit_code}, stdout_len={len(stdout_compressed)}, stderr_len={len(result.stderr)}")
    logger.debug(f"[bash_tool] stdout: {stdout_compressed[:500]}")
    if result.stderr:
        logger.debug(f"[bash_tool] stderr: {result.stderr[:500]}")

    return {
        "exit_code": result.exit_code,
        "stdout": stdout_compressed,
        "stderr": result.stderr,
        "error": None,
    }
