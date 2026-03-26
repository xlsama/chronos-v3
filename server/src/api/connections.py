import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import BatchTestItem, BatchTestResponse
from src.db.connection import get_session
from src.db.models import Server, Service
from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.ssh import SSHConnector
from src.services.crypto import CryptoService
from src.services.server_service import ServerService
from src.services.service_service import ServiceService

log = get_logger()

router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.post("/test-all", response_model=BatchTestResponse)
async def test_all_connections(
    session: AsyncSession = Depends(get_session),
):
    crypto = CryptoService(key=get_settings().encryption_key)

    services = list(
        (await session.execute(select(Service).order_by(Service.created_at.desc())))
        .scalars()
        .all()
    )
    servers = list(
        (await session.execute(select(Server).order_by(Server.created_at.desc())))
        .scalars()
        .all()
    )

    svc_service = ServiceService(session=session, crypto=crypto)
    srv_service = ServerService(session=session, crypto=crypto)

    async def _test_service(service: Service) -> BatchTestItem:
        try:
            success, message = await svc_service.test_connection(service)
            service.status = "online" if success else "offline"
            return BatchTestItem(
                id=service.id,
                name=service.name,
                type="service",
                success=success,
                message=message,
            )
        except Exception as e:
            service.status = "offline"
            return BatchTestItem(
                id=service.id,
                name=service.name,
                type="service",
                success=False,
                message=str(e),
            )

    async def _test_server(server: Server) -> BatchTestItem:
        try:
            password, private_key = srv_service.get_decrypted_credentials(server)
            bastion_pw, bastion_pk = srv_service.get_decrypted_bastion_credentials(server)
            connector = SSHConnector(
                host=server.host,
                port=server.port,
                username=server.username,
                password=password,
                private_key=private_key,
                bastion_host=server.bastion_host,
                bastion_port=server.bastion_port,
                bastion_username=server.bastion_username,
                bastion_password=bastion_pw,
                bastion_private_key=bastion_pk,
            )
            ok = await connector.test_connection()
            server.status = "online" if ok else "offline"
            return BatchTestItem(
                id=server.id,
                name=server.name,
                type="server",
                success=ok,
                message="SSH 连接测试成功" if ok else "SSH 连接测试失败",
            )
        except Exception as e:
            server.status = "offline"
            return BatchTestItem(
                id=server.id,
                name=server.name,
                type="server",
                success=False,
                message=str(e),
            )

    tasks = [_test_service(s) for s in services] + [_test_server(s) for s in servers]
    results = await asyncio.gather(*tasks)

    await session.commit()

    success_count = sum(1 for r in results if r.success)
    total = len(results)

    log.info("批量测试连接完成", total=total, success=success_count, failure=total - success_count)

    return BatchTestResponse(
        results=list(results),
        total=total,
        success_count=success_count,
        failure_count=total - success_count,
    )
