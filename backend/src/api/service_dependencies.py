import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ServiceDependencyCreate, ServiceDependencyResponse
from src.db.connection import get_session
from src.lib.errors import NotFoundError
from src.services.service_dependency_service import ServiceDependencyService

router = APIRouter(prefix="/api/service-dependencies", tags=["service-dependencies"])


@router.post("", response_model=ServiceDependencyResponse)
async def create_service_dependency(
    body: ServiceDependencyCreate,
    session: AsyncSession = Depends(get_session),
):
    return await ServiceDependencyService(session).create(**body.model_dump())


@router.get("/by-project/{project_id}", response_model=list[ServiceDependencyResponse])
async def list_service_dependencies_by_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await ServiceDependencyService(session).list_by_project(project_id)


@router.delete("/{dependency_id}")
async def delete_service_dependency(
    dependency_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    ok = await ServiceDependencyService(session).delete(dependency_id)
    if not ok:
        raise NotFoundError("Service dependency not found")
    return {"ok": True}
