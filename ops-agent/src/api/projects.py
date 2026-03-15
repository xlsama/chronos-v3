import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ProjectCloudMdUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from src.db.connection import get_session
from src.lib.errors import NotFoundError
from src.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.create(**body.model_dump())
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(session: AsyncSession = Depends(get_session)):
    service = ProjectService(session=session)
    return await service.list()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")
    return await service.update(project, **body.model_dump(exclude_unset=True))


@router.patch("/{project_id}/cloud-md", response_model=ProjectResponse)
async def update_cloud_md(
    project_id: uuid.UUID,
    body: ProjectCloudMdUpdate,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")
    return await service.update_cloud_md(project, body.cloud_md)


@router.delete("/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")
    await service.delete(project)
    return {"ok": True}
