import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ServiceConnectionBindingCreate, ServiceConnectionBindingResponse
from src.db.connection import get_session
from src.lib.errors import NotFoundError
from src.services.service_binding_service import ServiceBindingService

router = APIRouter(prefix="/api/service-bindings", tags=["service-bindings"])


@router.post("", response_model=ServiceConnectionBindingResponse)
async def create_service_binding(
    body: ServiceConnectionBindingCreate,
    session: AsyncSession = Depends(get_session),
):
    return await ServiceBindingService(session).create(**body.model_dump())


@router.get("/by-project/{project_id}", response_model=list[ServiceConnectionBindingResponse])
async def list_service_bindings_by_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await ServiceBindingService(session).list_by_project(project_id)


@router.delete("/{binding_id}")
async def delete_service_binding(
    binding_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    ok = await ServiceBindingService(session).delete(binding_id)
    if not ok:
        raise NotFoundError("Service binding not found")
    return {"ok": True}
