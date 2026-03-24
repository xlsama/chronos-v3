import asyncio
import re
import time
import uuid

from src.lib.logger import get_logger
from src.ops_agent.ssh import SSHConnector
from src.ops_agent.tools.tool_permissions import ShellSafety, CommandType, compress_output

log = get_logger(component="ssh_bash")

# 匹配 2>/dev/null 和 2> /dev/null（含前导空白）
_STDERR_DISCARD_RE = re.compile(r'\s*2>\s*/dev/null')


def _strip_stderr_discard(command: str) -> str:
    """去除命令中的 2>/dev/null，确保 stderr 始终被保留。"""
    return _STDERR_DISCARD_RE.sub('', command)


# Permission denied 自动 sudo 重试
_PERMISSION_DENIED_PATTERNS = [
    "permission denied",
    "operation not permitted",
    "access denied",
]


def _is_permission_denied(exit_code: int, stdout: str, stderr: str) -> bool:
    """检查命令输出是否为权限错误。"""
    if exit_code == 0:
        return False
    combined = (stdout + stderr).lower()
    # 目标机没有 sudo，重试无意义
    if "sudo: command not found" in combined or "sudo: not found" in combined:
        return False
    return any(p in combined for p in _PERMISSION_DENIED_PATTERNS)

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
    from src.env import get_settings
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
        sudo_password = service.get_sudo_password(server)

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
            sudo_password=sudo_password,
        )

        async with _registry_lock:
            _connector_registry[server_id] = (connector, time.monotonic())
        return connector


async def list_servers() -> list[dict]:
    """List available servers, excluding offline ones."""
    from sqlalchemy import select

    from src.db.connection import get_session_factory
    from src.db.models import Server

    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Server).where(Server.status != "offline")
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


async def ssh_bash(server_id: str, command: str) -> dict:
    """Execute a shell command on the target server via SSH."""
    cmd_type = ShellSafety.classify(command)

    log.info("Executing", server=server_id[:8], cmd_type=cmd_type.name, command_len=len(command))
    log.debug("Executing", server=server_id[:8], command=command)

    if cmd_type == CommandType.BLOCKED:
        log.warning("BLOCKED", command=command)
        return {"error": "命令被系统拦截：此命令过于危险，禁止执行"}

    try:
        connector = await get_connector(server_id)
    except ValueError as e:
        log.error("Connection error", error=str(e))
        return {"error": str(e)}

    # 执行前去除 2>/dev/null，确保 stderr 中的权限错误等信息不会丢失
    command = _strip_stderr_discard(command)

    try:
        t0 = time.monotonic()
        result = await connector.execute(command)
        exec_elapsed = time.monotonic() - t0
    except (asyncio.TimeoutError, TimeoutError):
        actual_elapsed = time.monotonic() - t0
        log.warning("Timeout", elapsed=f"{actual_elapsed:.2f}s", limit=connector.timeout)
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"命令执行超时（{connector.timeout}秒）。如果是后台启动命令，进程可能已成功启动，请用 ps/pgrep 确认。",
            "error": None,
        }
    except (OSError, ConnectionError) as e:
        log.error("SSH connection failed", error=str(e))
        return {"error": f"SSH 连接失败: {e}"}
    except Exception as e:
        log.error("Unexpected error", error=str(e))
        return {"error": f"执行异常: {e}"}

    # 自动 sudo 重试：仅限 READ 命令 + permission denied + 非 sudo 命令
    if (
        cmd_type == CommandType.READ
        and _is_permission_denied(result.exit_code, result.stdout, result.stderr)
        and not command.lstrip().startswith("sudo")
    ):
        sudo_command = f"sudo {command}"
        log.info(
            "Permission denied on READ cmd, auto-retrying with sudo",
            server=server_id[:8],
            original=command,
        )
        try:
            retry_result = await connector.execute(sudo_command)
            if not _is_permission_denied(
                retry_result.exit_code, retry_result.stdout, retry_result.stderr
            ):
                retry_elapsed = time.monotonic() - t0
                stdout_compressed = compress_output(retry_result.stdout)
                log.info(
                    "Sudo retry succeeded",
                    elapsed=f"{retry_elapsed:.2f}s",
                    exit_code=retry_result.exit_code,
                    stdout_len=len(stdout_compressed),
                )
                return {
                    "exit_code": retry_result.exit_code,
                    "stdout": stdout_compressed,
                    "stderr": retry_result.stderr,
                    "error": None,
                }
            log.warning("Sudo retry also got permission denied")
        except (asyncio.TimeoutError, TimeoutError):
            log.warning("Sudo retry timed out")
        except Exception as e:
            log.warning("Sudo retry failed", error=str(e))

    stdout_compressed = compress_output(result.stdout)
    log.info("Result", elapsed=f"{exec_elapsed:.2f}s", exit_code=result.exit_code, stdout_len=len(stdout_compressed), stderr_len=len(result.stderr))
    log.debug("stdout", stdout=stdout_compressed)
    if result.stderr:
        log.debug("stderr", stderr=result.stderr)

    return {
        "exit_code": result.exit_code,
        "stdout": stdout_compressed,
        "stderr": result.stderr,
        "error": None,
    }
