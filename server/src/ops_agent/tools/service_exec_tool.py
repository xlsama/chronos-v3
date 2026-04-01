import asyncio
import time
import uuid

from langchain_core.tools import StructuredTool

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.tools.base_tool import BaseTool, PermissionBehavior, PermissionResult
from src.ops_agent.tools.truncation import truncate_output
from src.ops_agent.tools.service_connectors.base import ServiceConnector
from src.ops_agent.tools.safety import CommandType, ServiceSafety

log = get_logger(component="service_exec")

# ── Service Exec Tool Prompt ──

_SERVICE_EXEC_PROMPT = """\
绕过 SSH 直接连接服务执行命令/查询。

## 支持的服务类型及命令语法

| 类型 | 命令格式 | 示例 |
|------|----------|------|
| PostgreSQL | SQL | SELECT * FROM pg_stat_activity LIMIT 10 |
| MySQL | SQL | SHOW PROCESSLIST; SELECT ... LIMIT 10 |
| Redis | Redis 命令 | INFO, GET key, KEYS pattern*, DBSIZE |
| Prometheus | PromQL | up, rate(http_requests_total[5m]) |
| MongoDB | JSON 命令 | {"find":"coll","filter":{},"limit":10} |
| Elasticsearch | REST 路径 | GET /_cluster/health |
| Doris/StarRocks | SQL | 同 MySQL 语法 |
| Kubernetes | kubectl 命令 | get pods -n default |
| Docker | Docker 命令 | ps, inspect <id> |
| Jenkins | API 路径 | GET /api/json |
| Hive | HiveQL | SHOW DATABASES; SELECT ... LIMIT 10 |

## 参数
- service_id（必填）：必须是 list_services() 返回的有效 UUID
- command（必填）：要执行的命令/查询
- explanation（写操作时必填）：说明操作原因和预期影响

## 前置条件
首次使用前必须调用 list_services() 获取有效的 service_id 和 service_type。
根据 service_type 选择正确的命令语法。

## 返回格式
纯文本字符串（查询结果或错误信息）。

## 安全规则
- SELECT/只读查询自动执行
- INSERT/UPDATE/DELETE 等 DML 需人工审批
- DROP/TRUNCATE/ALTER 等 DDL 被拦截
- 各服务类型有独立的安全分类规则

## 最佳实践
- 数据查询必须加 LIMIT，避免全表扫描
- 先查服务健康状态再查业务数据
- 慢查询用 EXPLAIN 分析执行计划（MySQL/PostgreSQL）
- Redis 避免 KEYS * 在生产环境（用 SCAN 替代）
- ES 优先检查 /_cluster/health 判断集群状态
- Prometheus 查询注意时间范围，避免拉取过多数据
- 写操作必须在 explanation 中说明原因和风险
"""

# Registry of service connectors with TTL and capacity management
_connector_registry: dict[str, tuple[ServiceConnector, float]] = {}
_registry_lock = asyncio.Lock()
_CONNECTOR_TTL = 600  # 10 minutes
_CONNECTOR_MAX_SIZE = 50

CONNECTOR_MAP: dict[str, type] = {}


def _load_connector_map():
    """Lazy-load connector classes to avoid import errors at module level."""
    global CONNECTOR_MAP
    if CONNECTOR_MAP:
        return
    from src.ops_agent.tools.service_connectors.postgresql import PostgreSQLConnector
    from src.ops_agent.tools.service_connectors.redis_conn import RedisConnector
    from src.ops_agent.tools.service_connectors.prometheus import PrometheusConnector
    from src.ops_agent.tools.service_connectors.mysql import MySQLConnector
    from src.ops_agent.tools.service_connectors.mongodb import MongoDBConnector
    from src.ops_agent.tools.service_connectors.elasticsearch import ElasticsearchConnector
    from src.ops_agent.tools.service_connectors.doris import DorisConnector
    from src.ops_agent.tools.service_connectors.starrocks import StarRocksConnector
    from src.ops_agent.tools.service_connectors.jenkins import JenkinsConnector
    from src.ops_agent.tools.service_connectors.kettle import KettleConnector
    from src.ops_agent.tools.service_connectors.hive import HiveConnector
    from src.ops_agent.tools.service_connectors.kubernetes import KubernetesConnector
    from src.ops_agent.tools.service_connectors.docker_conn import DockerConnector

    CONNECTOR_MAP = {
        "postgresql": PostgreSQLConnector,
        "mysql": MySQLConnector,
        "redis": RedisConnector,
        "prometheus": PrometheusConnector,
        "mongodb": MongoDBConnector,
        "elasticsearch": ElasticsearchConnector,
        "doris": DorisConnector,
        "starrocks": StarRocksConnector,
        "jenkins": JenkinsConnector,
        "kettle": KettleConnector,
        "hive": HiveConnector,
        "kubernetes": KubernetesConnector,
        "docker": DockerConnector,
    }


def _evict_expired() -> None:
    """Remove expired connectors (must be called under lock)."""
    now = time.monotonic()
    expired = [k for k, (_, ts) in _connector_registry.items() if now - ts > _CONNECTOR_TTL]
    for k in expired:
        del _connector_registry[k]


async def invalidate_service_connector(service_id: str) -> None:
    """Remove a service connector from cache, e.g. after credentials update."""
    async with _registry_lock:
        entry = _connector_registry.pop(service_id, None)
    if entry:
        connector, _ = entry
        try:
            await connector.close()
        except Exception:
            pass


async def get_service_connector(service_id: str) -> ServiceConnector:
    """Get or create a service connector by service_id."""
    async with _registry_lock:
        _evict_expired()

        if service_id in _connector_registry:
            connector, _ = _connector_registry[service_id]
            _connector_registry[service_id] = (connector, time.monotonic())
            return connector

        if len(_connector_registry) >= _CONNECTOR_MAX_SIZE:
            oldest_key = min(_connector_registry, key=lambda k: _connector_registry[k][1])
            entry = _connector_registry.pop(oldest_key)
            try:
                await entry[0].close()
            except Exception:
                pass

    # Cache miss → query DB → create connector → cache
    from src.env import get_settings
    from src.db.connection import get_session_factory
    from src.db.models import Service
    from src.services.crypto import CryptoService

    factory = get_session_factory()
    async with factory() as session:
        try:
            service_uuid = uuid.UUID(service_id)
        except ValueError:
            raise ValueError(
                f"Invalid service_id '{service_id}': not a valid UUID. "
                f"Call list_services() to get valid service IDs."
            )
        service = await session.get(Service, service_uuid)
        if not service:
            raise ValueError(f"Service not found: {service_id}")

        crypto = CryptoService(key=get_settings().encryption_key)
        password = (
            crypto.decrypt(service.encrypted_password) if service.encrypted_password else None
        )
        config = service.config or {}

        connector = create_connector(
            service_type=service.service_type,
            host=service.host,
            port=service.port,
            password=password,
            config=config,
        )

        async with _registry_lock:
            _connector_registry[service_id] = (connector, time.monotonic())
        return connector


def create_connector(
    service_type: str,
    host: str,
    port: int,
    password: str | None,
    config: dict,
) -> ServiceConnector:
    """Create a ServiceConnector instance by service type and connection params."""
    _load_connector_map()

    connector_cls = CONNECTOR_MAP.get(service_type)
    if connector_cls is None:
        supported = ", ".join(CONNECTOR_MAP.keys())
        raise ValueError(f"不支持的服务类型: {service_type}，当前支持: {supported}")

    if service_type == "postgresql":
        return connector_cls(
            host=host,
            port=port,
            username=config.get("username", "postgres"),
            password=password,
            database=config.get("database", "postgres"),
        )
    elif service_type == "mysql":
        return connector_cls(
            host=host,
            port=port,
            username=config.get("username", "root"),
            password=password,
            database=config.get("database", "mysql"),
        )
    elif service_type == "redis":
        db = 0
        db_str = config.get("database", "0")
        try:
            db = int(db_str) if db_str else 0
        except (ValueError, TypeError):
            db = 0
        return connector_cls(
            host=host,
            port=port,
            password=password,
            db=db,
        )
    elif service_type == "prometheus":
        return connector_cls(
            host=host,
            port=port,
            use_tls=config.get("use_tls", False),
            path=config.get("path", ""),
            username=config.get("username"),
            password=password,
        )
    elif service_type == "mongodb":
        return connector_cls(
            host=host,
            port=port,
            username=config.get("username"),
            password=password,
            database=config.get("database", "admin"),
            auth_source=config.get("auth_source"),
        )
    elif service_type == "elasticsearch":
        return connector_cls(
            host=host,
            port=port,
            use_tls=config.get("use_tls", False),
            username=config.get("username"),
            password=password,
        )
    elif service_type in ("doris", "starrocks"):
        return connector_cls(
            host=host,
            port=port,
            username=config.get("username", "root"),
            password=password,
            database=config.get("database", ""),
        )
    elif service_type == "jenkins":
        return connector_cls(
            host=host,
            port=port,
            use_tls=config.get("use_tls", False),
            path=config.get("path", ""),
            username=config.get("username"),
            password=password,
        )
    elif service_type == "kettle":
        return connector_cls(
            host=host,
            port=port,
            use_tls=config.get("use_tls", False),
            username=config.get("username"),
            password=password,
        )
    elif service_type == "hive":
        return connector_cls(
            host=host,
            port=port,
            username=config.get("username", "hive"),
            password=password,
            database=config.get("database", "default"),
        )
    elif service_type == "kubernetes":
        if not password:
            raise ValueError("Kubernetes 服务需要提供 kubeconfig 内容")
        return connector_cls(
            host=host,
            port=port,
            kubeconfig=password,
            default_namespace=config.get("default_namespace", "default"),
            context=config.get("context"),
        )
    elif service_type == "docker":
        return connector_cls(
            host=host,
            port=port,
            use_tls=config.get("use_tls", False),
            tls_certs=password if config.get("use_tls", False) else None,
        )
    else:
        raise ValueError(f"不支持的服务类型: {service_type}")


async def list_services() -> list[dict]:
    """List available services, excluding offline ones."""
    from sqlalchemy import select

    from src.db.connection import get_session_factory
    from src.db.models import Service

    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Service).where(Service.status != "offline")
        result = await session.execute(stmt)
        services = result.scalars().all()

        return [
            {
                "id": str(s.id),
                "name": s.name,
                "service_type": s.service_type,
                "host": s.host,
                "port": s.port,
                "status": s.status,
            }
            for s in services
        ]


async def get_service_type(service_id: str) -> str:
    """Lookup service_type for a given service_id."""
    if not service_id:
        return ""
    try:
        from src.db.connection import get_session_factory
        from src.db.models import Service

        async with get_session_factory()() as session:
            svc = await session.get(Service, uuid.UUID(service_id))
            return svc.service_type if svc else ""
    except Exception:
        return ""


async def _execute_service(service_id: str, command: str) -> str:
    """Execute a command on a service (internal implementation). Returns plain text string."""
    try:
        connector = await get_service_connector(service_id)
    except ValueError as e:
        return f"错误: {e}"

    # Defense-in-depth: always block dangerous commands
    cmd_type = ServiceSafety.classify(connector.service_type, command)
    if cmd_type == CommandType.BLOCKED:
        return "命令被系统拦截"

    log.info(
        "Executing",
        service=service_id[:8],
        type=connector.service_type,
        cmd_type=cmd_type.name,
        command=command[:100],
    )

    try:
        t0 = time.monotonic()
        settings = get_settings()
        result = await asyncio.wait_for(
            connector.execute(command), timeout=settings.command_timeout
        )
        exec_elapsed = time.monotonic() - t0
        log.info("Completed", elapsed=f"{exec_elapsed:.2f}s")
    except asyncio.TimeoutError:
        actual_elapsed = time.monotonic() - t0
        timeout_val = get_settings().command_timeout
        log.warning("Timeout", elapsed=f"{actual_elapsed:.2f}s", limit=f"{timeout_val}s")
        await invalidate_service_connector(service_id)
        return f"命令执行超时（{timeout_val}秒），可能原因: 查询耗时过长、表锁/死锁、连接阻塞等"
    except Exception as e:
        log.error("Error", error=str(e))
        await invalidate_service_connector(service_id)
        return f"执行异常: {e}"

    if not result.success:
        return f"执行失败: {result.error}"
    return result.output


class ServiceExecTool(BaseTool):
    """直连服务命令执行工具（PostgreSQL/MySQL/Redis/Prometheus 等）。"""

    @property
    def name(self) -> str:
        return "service_exec"

    @property
    def summary(self) -> str:
        return "直连服务执行命令（PostgreSQL/MySQL/Redis/Prometheus 等）"

    @property
    def prompt(self) -> str:
        return _SERVICE_EXEC_PROMPT

    def is_read_only(self, **kwargs) -> bool:
        # 无法同步获取 service_type，保守返回 False
        return False

    def is_concurrency_safe(self, **kwargs) -> bool:
        return False

    async def check_permissions(self, **kwargs) -> PermissionResult:
        service_id = kwargs.get("service_id", "")
        command = kwargs.get("command", "")
        service_type = await get_service_type(service_id)
        cmd_type = ServiceSafety.classify(service_type, command)
        if cmd_type == CommandType.BLOCKED:
            return PermissionResult(PermissionBehavior.DENY, "命令被系统拦截")
        if cmd_type == CommandType.DANGEROUS:
            return PermissionResult(PermissionBehavior.ASK, risk_level="HIGH")
        if cmd_type == CommandType.WRITE:
            return PermissionResult(PermissionBehavior.ASK, risk_level="MEDIUM")
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kwargs) -> str:
        return await _execute_service(kwargs.get("service_id", ""), kwargs.get("command", ""))

    def _build_langchain_tool(self):
        tool_self = self

        async def _execute(service_id: str, command: str, explanation: str = "") -> str:
            result = await tool_self.execute(service_id=service_id, command=command)
            return truncate_output(result, tool_self.max_result_size_chars)

        return StructuredTool.from_function(
            coroutine=_execute,
            name=self.name,
            description=self.prompt,
        )
