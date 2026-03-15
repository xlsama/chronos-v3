import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ConnectionTestResponse,
    InfrastructureCreate,
    InfrastructureResponse,
)
from src.config import get_settings
from src.connectors.ssh import SSHConnector
from src.db.connection import get_session
from src.db.models import Infrastructure
from src.lib.errors import NotFoundError
from src.services.crypto import CryptoService
from src.services.infrastructure_service import InfrastructureService

router = APIRouter(prefix="/api/infrastructures", tags=["infrastructures"])


def get_crypto() -> CryptoService:
    return CryptoService(key=get_settings().encryption_key)


@router.post("", response_model=InfrastructureResponse)
async def create_infrastructure(
    body: InfrastructureCreate,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    service = InfrastructureService(session=session, crypto=crypto)
    infra = await service.create(**body.model_dump())
    return infra


@router.get("", response_model=list[InfrastructureResponse])
async def list_infrastructures(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Infrastructure).order_by(Infrastructure.created_at.desc()))
    return result.scalars().all()


@router.get("/{infra_id}", response_model=InfrastructureResponse)
async def get_infrastructure(
    infra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    infra = await session.get(Infrastructure, infra_id)
    if not infra:
        raise NotFoundError("Infrastructure not found")
    return infra


@router.delete("/{infra_id}")
async def delete_infrastructure(
    infra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    infra = await session.get(Infrastructure, infra_id)
    if not infra:
        raise NotFoundError("Infrastructure not found")
    await session.delete(infra)
    await session.commit()
    return {"ok": True}


@router.post("/{infra_id}/test", response_model=ConnectionTestResponse)
async def test_connection(
    infra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    infra = await session.get(Infrastructure, infra_id)
    if not infra:
        raise NotFoundError("Infrastructure not found")

    service = InfrastructureService(session=session, crypto=crypto)
    password, private_key = service.get_decrypted_credentials(infra)

    connector = SSHConnector(
        host=infra.host,
        port=infra.port,
        username=infra.username,
        password=password,
        private_key=private_key,
    )

    ok = await connector.test_connection()

    infra.status = "online" if ok else "offline"
    await session.commit()

    return ConnectionTestResponse(
        success=ok,
        message="Connection successful" if ok else "Connection failed",
    )
