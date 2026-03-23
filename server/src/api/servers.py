import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    BatchCreateResult,
    BatchServerCreate,
    PaginatedResponse,
    ServerCreate,
    ServerResponse,
    ServerTestResponse,
    ServerUpdate,
)
from src.env import get_settings
from src.ops_agent.ssh import SSHConnector
from src.db.connection import get_session
from src.db.models import Server
from src.lib.errors import NotFoundError
from src.lib.logger import get_logger
from src.services.server_service import ServerService
from src.services.crypto import CryptoService

log = get_logger()

router = APIRouter(prefix="/api/servers", tags=["servers"])


def get_crypto() -> CryptoService:
    return CryptoService(key=get_settings().encryption_key)


@router.post("", response_model=ServerResponse)
async def create_server(
    body: ServerCreate,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    service = ServerService(session=session, crypto=crypto)
    server = await service.create(**body.model_dump())
    return server


@router.post("/batch", response_model=BatchCreateResult)
async def batch_create_servers(
    body: BatchServerCreate,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    log.info("批量创建服务器: 开始", total_items=len(body.items))
    service = ServerService(session=session, crypto=crypto)
    created = 0
    skipped = 0
    errors: list[str] = []
    for i, item in enumerate(body.items):
        try:
            await service.create(**item.model_dump())
            created += 1
            log.info(
                "批量创建服务器: 成功",
                index=i,
                name=item.name,
                host=item.host,
                port=item.port,
                username=item.username,
            )
        except Exception as e:
            await session.rollback()
            msg = str(e).lower()
            if "already exists" in msg or "unique" in msg or "duplicate" in msg:
                skipped += 1
                log.warning("批量创建服务器: 跳过(已存在)", index=i, name=item.name)
            else:
                errors.append(f"{item.name}: {e}")
                log.error("批量创建服务器: 失败", index=i, name=item.name, error=str(e))
    log.info(
        "批量创建服务器: 完成",
        created=created,
        skipped=skipped,
        errors=len(errors),
    )
    return BatchCreateResult(created=created, skipped=skipped, errors=errors)


@router.get("", response_model=PaginatedResponse[ServerResponse])
async def list_servers(
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_session),
):
    total = await session.scalar(select(func.count()).select_from(Server)) or 0
    result = await session.execute(
        select(Server)
        .order_by(Server.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{server_id}", response_model=ServerResponse)
async def get_server(
    server_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    server = await session.get(Server, server_id)
    if not server:
        raise NotFoundError("Server not found")
    return server


@router.patch("/{server_id}", response_model=ServerResponse)
async def update_server(
    server_id: uuid.UUID,
    body: ServerUpdate,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    server = await session.get(Server, server_id)
    if not server:
        raise NotFoundError("Server not found")
    service = ServerService(session=session, crypto=crypto)
    return await service.update(server, **body.model_dump(exclude_unset=True))


@router.delete("/{server_id}", status_code=204)
async def delete_server(
    server_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    server = await session.get(Server, server_id)
    if not server:
        raise NotFoundError("Server not found")
    await session.delete(server)
    await session.commit()
    return Response(status_code=204)


@router.post("/{server_id}/test", response_model=ServerTestResponse)
async def test_server(
    server_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    server = await session.get(Server, server_id)
    if not server:
        raise NotFoundError("Server not found")

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

    ok = await connector.test_connection()

    server.status = "online" if ok else "offline"
    await session.commit()

    return ServerTestResponse(
        success=ok,
        message="Connection successful" if ok else "Connection failed",
    )
