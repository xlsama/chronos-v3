import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    PaginatedResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from src.db.connection import get_session
from src.db.models import Project, Server
from src.lib.errors import NotFoundError, ValidationError
from src.services.project_service import ProjectService
from src.services.service_map import ensure_service_map

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.create(**body.model_dump())
    await ensure_service_map(session, project.id, project.name)
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
    paged_items = items[start:start + page_size]
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

    # Handle linked_server_ids via junction table
    if "linked_server_ids" in data:
        server_ids = data.pop("linked_server_ids") or []
        if server_ids:
            result = await session.execute(
                select(Server.id).where(Server.id.in_(server_ids))
            )
            found = {row[0] for row in result}
            missing = set(server_ids) - found
            if missing:
                raise ValidationError(f"Servers not found: {', '.join(str(m) for m in missing)}")
        await service.set_linked_servers(project, server_ids)

    if data:
        project = await service.update(project, **data)

    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = ProjectService(session=session)
    project = await service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")
    await service.delete(project)
    return Response(status_code=204)
