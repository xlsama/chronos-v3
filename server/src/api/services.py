import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    PaginatedResponse,
    ServiceCreate,
    ServiceResponse,
    ServiceUpdate,
    ServerTestResponse,
)
from src.env import get_settings
from src.db.connection import get_session
from src.db.models import Service
from src.lib.errors import NotFoundError
from src.services.crypto import CryptoService
from src.services.service_service import ServiceService

router = APIRouter(prefix="/api/services", tags=["services"])


def _get_service_service(session: AsyncSession) -> ServiceService:
    crypto = CryptoService(key=get_settings().encryption_key)
    return ServiceService(session=session, crypto=crypto)


@router.post("", response_model=ServiceResponse)
async def create_service(
    body: ServiceCreate,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.create(**body.model_dump())
    return _to_response(service)


@router.get("", response_model=PaginatedResponse[ServiceResponse])
async def list_services(
    page: int = 1,
    page_size: int = 50,
    type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(func.count()).select_from(Service)
    if type:
        stmt = stmt.where(Service.service_type == type)
    total = await session.scalar(stmt) or 0

    svc = _get_service_service(session)
    items = await svc.list_all(service_type=type)
    start = (page - 1) * page_size
    paged = items[start : start + page_size]
    return PaginatedResponse(
        items=[_to_response(s) for s in paged],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.get(service_id)
    if not service:
        raise NotFoundError("Service not found")
    return _to_response(service)


@router.patch("/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: uuid.UUID,
    body: ServiceUpdate,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.get(service_id)
    if not service:
        raise NotFoundError("Service not found")
    data = body.model_dump(exclude_unset=True)
    service = await svc.update(service, **data)
    return _to_response(service)


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.get(service_id)
    if not service:
        raise NotFoundError("Service not found")
    await svc.delete(service)
    return Response(status_code=204)


@router.post("/{service_id}/test", response_model=ServerTestResponse)
async def test_service(
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.get(service_id)
    if not service:
        raise NotFoundError("Service not found")
    success, message = await svc.test_connection(service)
    # Update status
    service.status = "online" if success else "offline"
    await session.commit()
    return ServerTestResponse(success=success, message=message)


def _to_response(service: Service) -> ServiceResponse:
    return ServiceResponse(
        id=service.id,
        name=service.name,
        description=service.description,
        service_type=service.service_type,
        host=service.host,
        port=service.port,
        config=service.config or {},
        has_password=service.encrypted_password is not None,
        status=service.status,
        created_at=service.created_at,
        updated_at=service.updated_at,
    )
