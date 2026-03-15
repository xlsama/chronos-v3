import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import DocumentResponse, DocumentUpload
from src.db.connection import get_session
from src.lib.embedder import Embedder
from src.lib.errors import NotFoundError
from src.services.document_service import DocumentService
from src.services.project_service import ProjectService

router = APIRouter(tags=["documents"])


def get_embedder() -> Embedder:
    return Embedder()


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
