import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import DocumentResponse, DocumentUpload
from src.db.connection import get_session
from src.lib.embedder import Embedder
from src.lib.errors import NotFoundError
from src.lib.file_parsers import SUPPORTED_EXTENSIONS
from src.lib.image_describer import ImageDescriber
from src.services.document_service import DocumentService
from src.services.project_service import ProjectService

router = APIRouter(tags=["documents"])

_embedder_instance: Embedder | None = None
_image_describer_instance: ImageDescriber | None = None


def get_embedder() -> Embedder:
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = Embedder()
    return _embedder_instance


def get_image_describer() -> ImageDescriber:
    global _image_describer_instance
    if _image_describer_instance is None:
        _image_describer_instance = ImageDescriber()
    return _image_describer_instance


@router.post("/api/projects/{project_id}/documents", response_model=DocumentResponse)
async def upload_document(
    project_id: uuid.UUID,
    body: DocumentUpload,
    session: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
):
    project_service = ProjectService(session=session)
    project = await project_service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")

    service = DocumentService(session=session, embedder=embedder)
    doc = await service.upload(
        project_id=project_id,
        filename=body.filename,
        content=body.content,
        doc_type=body.doc_type,
    )
    return doc


@router.post("/api/projects/{project_id}/documents/upload", response_model=DocumentResponse)
async def upload_document_file(
    project_id: uuid.UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder),
    image_describer: ImageDescriber = Depends(get_image_describer),
):
    """Upload a binary file (PDF, Word, Excel, CSV, Markdown, Text, Image)."""
    project_service = ProjectService(session=session)
    project = await project_service.get(project_id)
    if not project:
        raise NotFoundError("Project not found")

    filename = file.filename or "unknown"
    from pathlib import Path
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        from src.lib.errors import AppError
        raise AppError(
            f"Unsupported file format: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            status_code=400,
        )

    file_bytes = await file.read()
    service = DocumentService(session=session, embedder=embedder, image_describer=image_describer)
    doc = await service.upload_file(
        project_id=project_id,
        project_slug=project.slug,
        filename=filename,
        file_bytes=file_bytes,
    )
    return doc


@router.get("/api/projects/{project_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = DocumentService(session=session, embedder=None)  # embedder not needed for list
    return await service.list_by_project(project_id)


@router.delete("/api/documents/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    service = DocumentService(session=session, embedder=None)
    try:
        await service.delete(document_id)
    except ValueError as e:
        raise NotFoundError(str(e))
    return {"ok": True}
