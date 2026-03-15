import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DocumentChunk, ProjectDocument
from src.lib.chunker import chunk_text
from src.lib.embedder import Embedder


class DocumentService:
    def __init__(self, session: AsyncSession, embedder: Embedder):
        self.session = session
        self.embedder = embedder

    async def upload(
        self,
        project_id: uuid.UUID,
        filename: str,
        content: str,
        doc_type: str,
    ) -> ProjectDocument:
        doc = ProjectDocument(
            project_id=project_id,
            filename=filename,
            content=content,
            doc_type=doc_type,
            status="processing",
        )
        self.session.add(doc)
        await self.session.flush()  # get doc.id

        chunks = chunk_text(content)
        embeddings = await self.embedder.embed_texts(chunks)

        chunk_models = [
            DocumentChunk(
                document_id=doc.id,
                project_id=project_id,
                chunk_index=i,
                content=chunk,
                embedding=embedding,
            )
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        self.session.add_all(chunk_models)

        doc.status = "ready"
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def list_by_project(self, project_id: uuid.UUID) -> list[ProjectDocument]:
        result = await self.session.execute(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
            .order_by(ProjectDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, document_id: uuid.UUID) -> None:
        doc = await self.session.get(ProjectDocument, document_id)
        if not doc:
            raise ValueError("Document not found")
        await self.session.delete(doc)
        await self.session.commit()
