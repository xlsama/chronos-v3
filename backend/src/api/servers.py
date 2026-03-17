import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ServerCreate,
    ServerResponse,
    ServerTestResponse,
    ServerUpdate,
)
from src.config import get_settings
from src.ops_agent.ssh import SSHConnector
from src.db.connection import get_session
from src.db.models import Server
from src.lib.errors import NotFoundError
from src.services.server_service import ServerService
from src.services.crypto import CryptoService

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


@router.get("", response_model=list[ServerResponse])
async def list_servers(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Server).order_by(Server.created_at.desc()))
    return result.scalars().all()


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


@router.delete("/{server_id}")
async def delete_server(
    server_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    server = await session.get(Server, server_id)
    if not server:
        raise NotFoundError("Server not found")
    await session.delete(server)
    await session.commit()
    return {"ok": True}


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
