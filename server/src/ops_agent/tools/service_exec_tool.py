import asyncio
import time
import uuid

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.tools.tool_classifier import ServiceSafety, CommandType
from src.ops_agent.tools.service_connectors.base import ServiceConnector

log = get_logger(component="service_exec")

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


async def service_exec(service_id: str, command: str) -> str:
    """Execute a command on a service. Returns plain text string."""
    try:
        connector = await get_service_connector(service_id)
    except ValueError as e:
        return f"错误: {e}"

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
