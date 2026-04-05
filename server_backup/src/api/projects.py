import shutil
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ExtractedConnections,
    PaginatedResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from src.db.connection import get_session
from src.db.models import Project
from src.lib.errors import NotFoundError
from src.lib.paths import knowledge_dir
from src.services.project_service import ProjectService
from src.services.memory_md import ensure_memory_md
from src.services.import_connections_service import ImportConnectionsService

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.create(**body.model_dump())
    await ensure_memory_md(session, project.id, project.name, project.slug)
    await session.commit()
    return project


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_session),
):
    total = await session.scalar(select(func.count()).select_from(Project)) or 0
    service = ProjectService(session=session)
    items = await service.list_all()
    # Apply pagination manually (service.list already orders by created_at desc)
    start = (page - 1) * page_size
    paged_items = items[start : start + page_size]
    return PaginatedResponse(items=paged_items, total=total, page=page, page_size=page_size)


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

    data = body.model_dump(exclude_unset=True)
    if data:
        project = await service.update(project, **data)

    return project


@router.post("/{project_id}/import-connections", response_model=ExtractedConnections)
async def import_connections(
    project_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    project_service = ProjectService(session=session)
    project = await project_service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")

    service = ImportConnectionsService(session=session)
    return await service.extract(project_id, disconnect_check=request.is_disconnected)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")
    slug = project.slug
    await service.delete(project)
    knowledge_path = knowledge_dir(slug)
    if knowledge_path.exists():
        shutil.rmtree(knowledge_path)
    return Response(status_code=204)
