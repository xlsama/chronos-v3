import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from src.db.connection import get_session
from src.db.models import Server
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

    data = body.model_dump(exclude_unset=True)

    # Validate linked_server_ids if provided
    if "linked_server_ids" in data and data["linked_server_ids"] is not None:
        server_ids = data["linked_server_ids"]
        if server_ids:
            result = await session.execute(
                select(Server.id).where(Server.id.in_(server_ids))
            )
            found = {row[0] for row in result}
            missing = set(server_ids) - found
            if missing:
                raise ValidationError(f"Servers not found: {', '.join(str(m) for m in missing)}")
        # Store as string list for JSONB
        data["linked_server_ids"] = [str(sid) for sid in server_ids]

    return await service.update(project, **data)


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
