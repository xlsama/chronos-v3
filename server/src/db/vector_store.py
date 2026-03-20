import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DocumentChunk, Project, ProjectDocument


class VectorStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(
        self,
        query_embedding: list[float],
        project_id: uuid.UUID,
        limit: int = 5,
    ) -> list[dict]:
        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_metadata,
                ProjectDocument.filename,
                DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .join(ProjectDocument, DocumentChunk.document_id == ProjectDocument.id)
            .where(DocumentChunk.project_id == project_id)
            .where(DocumentChunk.embedding.isnot(None))
            .order_by("distance")
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "id": str(row.id),
                "document_id": str(row.document_id),
                "content": row.content,
                "chunk_index": row.chunk_index,
                "metadata": row.chunk_metadata or {},
                "filename": row.filename,
                "distance": row.distance,
            }
            for row in rows
        ]

    async def search_all(
        self,
        query_embedding: list[float],
        limit: int = 20,
    ) -> list[dict]:
        """Search across all projects, returning results with project metadata."""
        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.content,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_metadata,
                DocumentChunk.project_id,
                ProjectDocument.filename,
                Project.name.label("project_name"),
                Project.description.label("project_description"),
                DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .join(ProjectDocument, DocumentChunk.document_id == ProjectDocument.id)
            .join(Project, DocumentChunk.project_id == Project.id)
            .where(DocumentChunk.embedding.isnot(None))
            .order_by("distance")
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "id": str(row.id),
                "document_id": str(row.document_id),
                "content": row.content,
                "chunk_index": row.chunk_index,
                "metadata": row.chunk_metadata or {},
                "filename": row.filename,
                "distance": row.distance,
                "project_id": str(row.project_id),
                "project_name": row.project_name,
                "project_description": row.project_description or "",
            }
            for row in rows
        ]
