import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import AttachmentResponse
from src.db.connection import get_session
from src.db.models import Attachment
from src.lib.errors import NotFoundError
from src.lib.file_parsers import SUPPORTED_EXTENSIONS, IMAGE_EXTENSIONS, parse_file
from src.lib.paths import uploads_dir
from src.lib.logger import get_logger

log = get_logger()

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

MAX_PARSED_CONTENT_LEN = 100_000


@router.post("", response_model=list[AttachmentResponse])
async def upload_files(
    files: list[UploadFile],
    incident_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    upload_path = uploads_dir()
    results: list[Attachment] = []

    for file in files:
        fname = file.filename or "file"
        ext = Path(fname).suffix.lower()
        stored_name = f"{uuid.uuid4()}{ext}"
        stored_path = upload_path / stored_name

        content = await file.read()
        stored_path.write_bytes(content)

        # Parse text content for supported document formats
        parsed_content = None
        if ext in SUPPORTED_EXTENSIONS and ext not in IMAGE_EXTENSIONS:
            try:
                parsed_content = await asyncio.to_thread(parse_file, content, fname)
                if parsed_content and len(parsed_content) > MAX_PARSED_CONTENT_LEN:
                    parsed_content = parsed_content[:MAX_PARSED_CONTENT_LEN] + "\n\n[内容过长，已截断]"
            except Exception as e:
                log.warning("Failed to parse attachment", filename=fname, error=str(e))

        attachment = Attachment(
            incident_id=incident_id,
            filename=fname,
            stored_filename=stored_name,
            content_type=file.content_type or "application/octet-stream",
            size=len(content),
            parsed_content=parsed_content,
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

    file_path = uploads_dir() / attachment.stored_filename
    if not file_path.exists():
        raise NotFoundError("File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=attachment.filename,
        media_type=attachment.content_type,
    )
