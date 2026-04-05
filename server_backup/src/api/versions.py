import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ContentVersionDetailResponse, ContentVersionResponse
from src.db.connection import get_session
from src.lib.errors import NotFoundError
from src.services.version_service import VersionService

router = APIRouter(prefix="/api/versions", tags=["versions"])


@router.get("", response_model=list[ContentVersionResponse])
async def list_versions(
    entity_type: str,
    entity_id: str,
    session: AsyncSession = Depends(get_session),
):
    service = VersionService(session)
    versions = await service.list_versions(entity_type, entity_id)
    return versions


@router.get("/{version_id}", response_model=ContentVersionDetailResponse)
async def get_version(
    version_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = VersionService(session)
    version = await service.get_version(version_id)
    if not version:
        raise NotFoundError("Version not found")
    return version
