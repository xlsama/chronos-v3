import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import IncidentHistoryListResponse, IncidentHistoryResponse
from src.db.connection import get_session
from src.lib.errors import NotFoundError
from src.services.incident_history_service import IncidentHistoryService

router = APIRouter(prefix="/api/incident-history", tags=["incident-history"])


@router.get("", response_model=IncidentHistoryListResponse)
async def list_incident_history(
    page: int = 1,
    page_size: int = 20,
    project_id: uuid.UUID | None = None,
    query: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    service = IncidentHistoryService(session=session)
    items, total = await service.list_all(
        page=page, page_size=page_size, project_id=project_id, query=query,
    )
    return IncidentHistoryListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{history_id}", response_model=IncidentHistoryResponse)
async def get_incident_history(
    history_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = IncidentHistoryService(session=session)
    record = await service.get(history_id)
    if not record:
        raise NotFoundError("Incident history not found")
    return record


@router.delete("/{history_id}")
async def delete_incident_history(
    history_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = IncidentHistoryService(session=session)
    deleted = await service.delete(history_id)
    if not deleted:
        raise NotFoundError("Incident history not found")
    return {"ok": True}
