import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionTestResponse,
    ConnectionUpdate,
)
from src.config import get_settings
from src.ops_agent.connectors.k8s import K8sConnector
from src.ops_agent.connectors.ssh import SSHConnector
from src.db.connection import get_session
from src.db.models import Connection
from src.lib.errors import NotFoundError
from src.services.connection_service import ConnectionService
from src.services.crypto import CryptoService

router = APIRouter(prefix="/api/connections", tags=["connections"])


def get_crypto() -> CryptoService:
    return CryptoService(key=get_settings().encryption_key)


@router.post("", response_model=ConnectionResponse)
async def create_connection(
    body: ConnectionCreate,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    service = ConnectionService(session=session, crypto=crypto)
    conn = await service.create(**body.model_dump())
    return conn


@router.get("", response_model=list[ConnectionResponse])
async def list_connections(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Connection).order_by(Connection.created_at.desc()))
    return result.scalars().all()


@router.get("/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    conn = await session.get(Connection, connection_id)
    if not conn:
        raise NotFoundError("Connection not found")
    return conn


@router.patch("/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: uuid.UUID,
    body: ConnectionUpdate,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    conn = await session.get(Connection, connection_id)
    if not conn:
        raise NotFoundError("Connection not found")
    service = ConnectionService(session=session, crypto=crypto)
    return await service.update(conn, **body.model_dump(exclude_unset=True))


@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    conn = await session.get(Connection, connection_id)
    if not conn:
        raise NotFoundError("Connection not found")
    await session.delete(conn)
    await session.commit()
    return {"ok": True}


@router.post("/{connection_id}/test", response_model=ConnectionTestResponse)
async def test_connection(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    conn = await session.get(Connection, connection_id)
    if not conn:
        raise NotFoundError("Connection not found")

    service = ConnectionService(session=session, crypto=crypto)

    if conn.type == "kubernetes":
        config = service.get_decrypted_conn_config(conn)
        if not config:
            return ConnectionTestResponse(success=False, message="Missing kubeconfig")
        connector = K8sConnector(
            kubeconfig=config["kubeconfig"],
            context=config.get("context"),
            namespace=config.get("namespace", "default"),
        )
    else:  # ssh
        password, private_key = service.get_decrypted_credentials(conn)
        connector = SSHConnector(
            host=conn.host,
            port=conn.port,
            username=conn.username,
            password=password,
            private_key=private_key,
        )

    ok = await connector.test_connection()

    conn.status = "online" if ok else "offline"
    await session.commit()

    return ConnectionTestResponse(
        success=ok,
        message="Connection successful" if ok else "Connection failed",
    )
