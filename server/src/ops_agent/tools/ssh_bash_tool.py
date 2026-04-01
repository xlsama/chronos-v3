import asyncio
import re
import time
import uuid

from langchain_core.tools import StructuredTool

from src.lib.logger import get_logger
from src.ops_agent.ssh import SSHConnector
from src.ops_agent.tools.base_tool import BaseTool, PermissionBehavior, PermissionResult
from src.ops_agent.tools.truncation import truncate_output
from src.ops_agent.tools.safety import CommandType, ShellSafety

log = get_logger(component="ssh_bash")

# ── SSH Bash Tool Prompt ──

_SSH_BASH_PROMPT = """\
通过 SSH 在目标服务器上执行 Shell 命令。

## 适用场景
- 检查远程服务器状态：进程、磁盘、内存、网络
- 查看应用日志：tail, grep, zcat
- Docker 容器操作：docker ps, docker logs, docker restart
- 系统服务管理：systemctl status/restart, journalctl -u

## 不适用
- 本地 Docker/K8s 操作 → 用 bash
- 数据库/缓存/监控查询 → 用 service_exec

## 参数
- server_id（必填）：必须是 list_servers() 返回的有效 UUID，不是主机名
- command（必填）：要执行的 Shell 命令
- explanation（写操作时必填）：说明操作原因和预期影响

## 前置条件
首次使用前必须调用 list_servers() 获取有效的 server_id。

## 返回格式
{"exit_code": 0, "stdout": "...", "stderr": "...", "error": null}
- exit_code=0 表示成功，非零表示失败
- error 非空表示系统级错误（连接失败、超时等）

## 安全规则
- 只读命令自动执行，写操作需人工审批，危险命令被拦截
- 系统自动去除 2>/dev/null，确保 stderr 中的权限错误等信息不丢失
- 权限不足时加 sudo 重试

## 跳板机/堡垒机
SSH 连接路径对 Agent 透明，无需手动指定跳板机。

## 最佳实践
- 先只读命令收集证据，再考虑写操作
- 用 tail -n 限制大文件输出，避免输出过大
- 多个查询命令用 && 串联：hostname && df -h && free -m
- 优先检查 Docker 容器状态：docker ps -a | grep <service>
- 进程存活不代表服务正常，接口超时时用 service_exec 检查依赖服务
- 超时后进程可能已启动，用 ps/pgrep 确认
- 写操作必须在 explanation 中说明原因和风险
"""

# 匹配 2>/dev/null 和 2> /dev/null（含前导空白）
_STDERR_DISCARD_RE = re.compile(r"\s*2>\s*/dev/null")


def _strip_stderr_discard(command: str) -> str:
    """去除命令中的 2>/dev/null，确保 stderr 始终被保留。"""
    return _STDERR_DISCARD_RE.sub("", command)


# Registry of connectors by server ID with TTL and capacity management
_connector_registry: dict[
    str, tuple[SSHConnector, float]
] = {}  # server_id -> (connector, last_used_time)
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


async def _execute_ssh(server_id: str, command: str) -> dict:
    """Execute a shell command on the target server via SSH (internal implementation)."""
    # Defense-in-depth: always block dangerous commands
    cmd_type = ShellSafety.classify(command)
    if cmd_type == CommandType.BLOCKED:
        log.warning("BLOCKED", command=command)
        return {"error": "命令被系统拦截：此命令过于危险，禁止执行"}

    log.info("Executing", server=server_id[:8], cmd_type=cmd_type.name, command_len=len(command))
    log.debug("Executing", server=server_id[:8], command=command)

    try:
        connector = await get_connector(server_id)
    except ValueError as e:
        log.error("Connection error", error=str(e))
        return {"exit_code": -1, "stdout": "", "stderr": "", "error": str(e)}

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
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": f"SSH 连接失败: {e}",
        }
    except Exception as e:
        log.error("Unexpected error", error=str(e))
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": f"执行异常: {type(e).__name__}: {e}",
        }

    stdout_compressed = result.stdout
    log.info(
        "Result",
        elapsed=f"{exec_elapsed:.2f}s",
        exit_code=result.exit_code,
        stdout_len=len(stdout_compressed),
        stderr_len=len(result.stderr),
    )
    log.debug("stdout", stdout=stdout_compressed)
    if result.stderr:
        log.debug("stderr", stderr=result.stderr)

    return {
        "exit_code": result.exit_code,
        "stdout": stdout_compressed,
        "stderr": result.stderr,
        "error": None,
    }


class SSHBashTool(BaseTool):
    """远程服务器 SSH 命令执行工具。"""

    @property
    def name(self) -> str:
        return "ssh_bash"

    @property
    def summary(self) -> str:
        return "在目标服务器执行 Shell 命令（通过 SSH）"

    @property
    def prompt(self) -> str:
        return _SSH_BASH_PROMPT

    def is_read_only(self, **kwargs) -> bool:
        return ShellSafety.classify(kwargs.get("command", "")) == CommandType.READ

    def is_destructive(self, **kwargs) -> bool:
        return ShellSafety.classify(kwargs.get("command", "")) == CommandType.DANGEROUS

    def is_concurrency_safe(self, **kwargs) -> bool:
        return self.is_read_only(**kwargs)

    async def check_permissions(self, **kwargs) -> PermissionResult:
        cmd_type = ShellSafety.classify(kwargs.get("command", ""))
        if cmd_type == CommandType.BLOCKED:
            return PermissionResult(PermissionBehavior.DENY, "命令被系统拦截")
        if cmd_type == CommandType.DANGEROUS:
            return PermissionResult(PermissionBehavior.ASK, risk_level="HIGH")
        if cmd_type == CommandType.WRITE:
            return PermissionResult(PermissionBehavior.ASK, risk_level="MEDIUM")
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kwargs) -> dict:
        return await _execute_ssh(kwargs.get("server_id", ""), kwargs.get("command", ""))

    def _build_langchain_tool(self):
        tool_self = self

        async def _execute(server_id: str, command: str, explanation: str = "") -> dict:
            result = await tool_self.execute(server_id=server_id, command=command)
            return truncate_output(result, tool_self.max_result_size_chars)

        return StructuredTool.from_function(
            coroutine=_execute,
            name=self.name,
            description=self.prompt,
        )
