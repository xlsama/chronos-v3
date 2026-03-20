import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Service
from src.services.crypto import CryptoService


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
        """Test connectivity to the service. Uses TCP socket for DB services, HTTP for web services."""
        try:
            if service.service_type in ("prometheus", "elasticsearch"):
                return await self._test_http(service)
            else:
                return await self._test_tcp(service)
        except Exception as e:
            return False, str(e)

    async def _test_tcp(self, service: Service) -> tuple[bool, str]:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(service.host, service.port),
                timeout=5,
            )
            writer.close()
            await writer.wait_closed()
            return True, f"TCP 连接 {service.host}:{service.port} 成功"
        except asyncio.TimeoutError:
            return False, f"连接 {service.host}:{service.port} 超时"
        except OSError as e:
            return False, f"连接 {service.host}:{service.port} 失败: {e}"

    async def _test_http(self, service: Service) -> tuple[bool, str]:
        import httpx

        scheme = "https" if service.config.get("use_tls") else "http"
        path = service.config.get("path", "/")
        if service.service_type == "prometheus":
            path = service.config.get("path", "/-/healthy")
        elif service.service_type == "elasticsearch":
            path = "/_cluster/health"

        url = f"{scheme}://{service.host}:{service.port}{path}"
        try:
            async with httpx.AsyncClient(timeout=5, verify=False) as client:
                resp = await client.get(url)
                if resp.status_code < 500:
                    return True, f"HTTP {resp.status_code} from {url}"
                return False, f"HTTP {resp.status_code} from {url}"
        except httpx.TimeoutException:
            return False, f"HTTP 请求 {url} 超时"
        except Exception as e:
            return False, f"HTTP 请求 {url} 失败: {e}"
