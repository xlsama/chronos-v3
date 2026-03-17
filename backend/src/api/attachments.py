import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import AttachmentResponse
from src.config import get_settings
from src.db.connection import get_session
from src.db.models import Attachment
from src.lib.errors import NotFoundError

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


@router.post("", response_model=list[AttachmentResponse])
async def upload_files(
    files: list[UploadFile],
    incident_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    results: list[Attachment] = []

    for file in files:
        ext = Path(file.filename or "file").suffix
        stored_name = f"{uuid.uuid4()}{ext}"
        stored_path = upload_dir / stored_name

        content = await file.read()
        stored_path.write_bytes(content)

        attachment = Attachment(
            incident_id=incident_id,
            filename=file.filename or "file",
            stored_filename=stored_name,
            content_type=file.content_type or "application/octet-stream",
            size=len(content),
        )
        session.add(attachment)
        results.append(attachment)

    await session.commit()
    for a in results:
        await session.refresh(a)
    return results


@router.get("/{attachment_id}/download")
async def download_file(
    attachment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    attachment = await session.get(Attachment, attachment_id)
    if not attachment:
        raise NotFoundError("Attachment not found")

    settings = get_settings()
    file_path = Path(settings.upload_dir) / attachment.stored_filename
    if not file_path.exists():
        raise NotFoundError("File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=attachment.filename,
        media_type=attachment.content_type,
    )
