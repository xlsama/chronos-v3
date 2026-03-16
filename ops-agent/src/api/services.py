import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import DiscoverServicesResponse, ServiceCreate, ServiceResponse
from src.db.connection import get_session
from src.lib.errors import NotFoundError
from src.services.service_catalog import ServiceCatalog

router = APIRouter(prefix="/api/services", tags=["services"])


@router.post("", response_model=ServiceResponse)
async def create_service(
    body: ServiceCreate,
    session: AsyncSession = Depends(get_session),
):
    catalog = ServiceCatalog(session)
    svc = await catalog.create(**body.model_dump())
    return svc


@router.get("/by-connection/{connection_id}", response_model=list[ServiceResponse])
async def list_services_by_connection(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    catalog = ServiceCatalog(session)
    return await catalog.list_by_connection(connection_id)


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    catalog = ServiceCatalog(session)
    svc = await catalog.get(service_id)
    if not svc:
        raise NotFoundError("Service not found")
    return svc


@router.delete("/{service_id}")
async def delete_service(
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    catalog = ServiceCatalog(session)
    ok = await catalog.delete(service_id)
    if not ok:
        raise NotFoundError("Service not found")
    return {"ok": True}


@router.post("/discover/{connection_id}", response_model=DiscoverServicesResponse)
async def discover_services(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    catalog = ServiceCatalog(session)
    services = await catalog.auto_discover(connection_id)
    await session.commit()
    return DiscoverServicesResponse(
        discovered=len(services),
        services=services,
    )
