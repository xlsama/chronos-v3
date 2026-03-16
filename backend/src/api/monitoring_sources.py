import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ConnectionTestResponse,
    MonitoringSourceCreate,
    MonitoringSourceResponse,
)
from src.config import get_settings
from src.ops_agent.connectors.loki import LokiConnector
from src.ops_agent.connectors.prometheus import PrometheusConnector
from src.db.connection import get_session
from src.lib.errors import NotFoundError
from src.services.crypto import CryptoService
from src.services.monitoring_source_service import MonitoringSourceService

router = APIRouter(prefix="/api/monitoring-sources", tags=["monitoring-sources"])


def get_crypto() -> CryptoService:
    return CryptoService(key=get_settings().encryption_key)


@router.post("", response_model=MonitoringSourceResponse)
async def create_monitoring_source(
    body: MonitoringSourceCreate,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    service = MonitoringSourceService(session=session, crypto=crypto)
    source = await service.create(**body.model_dump())
    return source


@router.get("/by-project/{project_id}", response_model=list[MonitoringSourceResponse])
async def list_monitoring_sources(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    crypto = CryptoService(key=get_settings().encryption_key)
    service = MonitoringSourceService(session=session, crypto=crypto)
    return await service.list_by_project(project_id)


@router.get("/{source_id}", response_model=MonitoringSourceResponse)
async def get_monitoring_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    crypto = CryptoService(key=get_settings().encryption_key)
    service = MonitoringSourceService(session=session, crypto=crypto)
    source = await service.get(source_id)
    if not source:
        raise NotFoundError("Monitoring source not found")
    return source


@router.delete("/{source_id}")
async def delete_monitoring_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    crypto = CryptoService(key=get_settings().encryption_key)
    service = MonitoringSourceService(session=session, crypto=crypto)
    ok = await service.delete(source_id)
    if not ok:
        raise NotFoundError("Monitoring source not found")
    return {"ok": True}


@router.post("/{source_id}/test", response_model=ConnectionTestResponse)
async def test_monitoring_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    crypto: CryptoService = Depends(get_crypto),
):
    service = MonitoringSourceService(session=session, crypto=crypto)
    source = await service.get(source_id)
    if not source:
        raise NotFoundError("Monitoring source not found")

    headers = None
    if source.conn_config:
        import orjson

        config = orjson.loads(crypto.decrypt(source.conn_config))
        if "auth_header" in config:
            headers = {"Authorization": config["auth_header"]}

    if source.source_type == "prometheus":
        connector = PrometheusConnector(endpoint=source.endpoint, headers=headers)
    elif source.source_type == "loki":
        connector = LokiConnector(endpoint=source.endpoint, headers=headers)
    else:
        return ConnectionTestResponse(success=False, message=f"Unknown type: {source.source_type}")

    ok = await connector.test_connection()

    source.status = "online" if ok else "offline"
    await session.commit()

    return ConnectionTestResponse(
        success=ok,
        message="Connection successful" if ok else "Connection failed",
    )
