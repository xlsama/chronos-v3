import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Service
from src.services.crypto import CryptoService

# Probe commands for each service type
_PROBE_COMMANDS: dict[str, str] = {
    "postgresql": "SELECT 1",
    "mysql": "SELECT 1",
    "redis": "PING",
    "mongodb": '{"ping": 1}',
    "prometheus": "up",
    "elasticsearch": "GET /_cluster/health",
    "doris": "SELECT 1",
    "starrocks": "SELECT 1",
    "jenkins": "GET /api/json",
    "kettle": "GET /kettle/status",
    "hive": "SELECT 1",
    "kubernetes": "kubectl cluster-info",
    "docker": "docker version",
}


class ServiceService:
    def __init__(self, session: AsyncSession, crypto: CryptoService):
        self.session = session
        self.crypto = crypto

    async def create(
        self,
        name: str,
        service_type: str,
        host: str,
        port: int,
        description: str | None = None,
        password: str | None = None,
        config: dict | None = None,
    ) -> Service:
        service = Service(
            name=name,
            description=description,
            service_type=service_type,
            host=host,
            port=port,
            config=config or {},
            encrypted_password=self.crypto.encrypt(password) if password else None,
        )
        self.session.add(service)
        await self.session.commit()
        await self.session.refresh(service)
        return service

    async def get(self, service_id: uuid.UUID) -> Service | None:
        return await self.session.get(Service, service_id)

    async def list_all(
        self, service_type: str | None = None
    ) -> list[Service]:
        stmt = select(Service).order_by(Service.created_at.desc())
        if service_type:
            stmt = stmt.where(Service.service_type == service_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, service: Service, **kwargs) -> Service:
        password = kwargs.pop("password", None)
        if password is not None:
            if password:
                service.encrypted_password = self.crypto.encrypt(password)
            else:
                service.encrypted_password = None

        for key, value in kwargs.items():
            if value is not None and hasattr(service, key):
                setattr(service, key, value)

        await self.session.commit()
        await self.session.refresh(service)

        from src.ops_agent.tools.service_exec_tool import invalidate_service_connector
        await invalidate_service_connector(str(service.id))

        return service

    async def delete(self, service: Service) -> None:
        service_id = str(service.id)
        await self.session.delete(service)
        await self.session.commit()

        from src.ops_agent.tools.service_exec_tool import invalidate_service_connector
        await invalidate_service_connector(service_id)

    async def test_connection(self, service: Service) -> tuple[bool, str]:
        """Test connectivity using real protocol-level probe (not just TCP port check)."""
        from src.ops_agent.tools.service_exec_tool import create_connector

        password = self.crypto.decrypt(service.encrypted_password) if service.encrypted_password else None
        config = service.config or {}

        try:
            connector = create_connector(
                service_type=service.service_type,
                host=service.host,
                port=service.port,
                password=password,
                config=config,
            )
        except ValueError as e:
            return False, str(e)

        probe = _PROBE_COMMANDS.get(service.service_type, "SELECT 1")
        try:
            result = await asyncio.wait_for(connector.execute(probe), timeout=10)
            if result.success:
                return True, f"{service.service_type} 服务连接测试成功"
            return False, f"探测命令失败: {result.error}"
        except asyncio.TimeoutError:
            return False, f"连接 {service.host}:{service.port} 超时（10秒）"
        except Exception as e:
            return False, _friendly_error(service.service_type, e)
        finally:
            try:
                await connector.close()
            except Exception:
                pass


def _friendly_error(service_type: str, exc: Exception) -> str:
    """Translate driver-level exceptions into user-friendly Chinese messages."""
    msg = str(exc).lower()

    # kubectl / Kubernetes errors
    if "unable to connect to the server" in msg:
        return "无法连接 K8s API Server，请检查 kubeconfig 和网络"
    if "unauthorized" in msg or ("forbidden" in msg and service_type == "kubernetes"):
        return "K8s 认证失败：kubeconfig 中的凭证无效或已过期"
    if "the server has asked for the client to provide credentials" in msg:
        return "K8s 认证失败：kubeconfig 中的凭证无效"

    # Authentication failures
    if any(kw in msg for kw in ("password authentication failed", "auth", "access denied", "authentication failed")):
        return "认证失败：用户名或密码错误"

    # Database does not exist
    if any(kw in msg for kw in ("does not exist", "unknown database", "no such database")):
        return "数据库不存在"

    # Connection refused
    if "connection refused" in msg or "connect call failed" in msg:
        return f"连接被拒绝：{service_type} 服务未启动或地址/端口错误"

    # DNS / hostname resolution
    if any(kw in msg for kw in ("nodename nor servname", "name or service not known", "getaddrinfo", "resolve")):
        return "主机名无法解析，请检查 host 配置"

    # Timeout
    if "timeout" in msg or "timed out" in msg:
        return "连接超时，请检查网络和防火墙设置"

    # Fallback: return original error
    return f"连接失败: {exc}"
