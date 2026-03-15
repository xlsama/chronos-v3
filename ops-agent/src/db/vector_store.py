import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DocumentChunk, ProjectDocument


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
                DocumentChunk.content,
                DocumentChunk.chunk_index,
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
                "content": row.content,
                "chunk_index": row.chunk_index,
                "filename": row.filename,
                "distance": row.distance,
            }
            for row in rows
        ]
