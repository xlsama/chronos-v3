import os
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DocumentChunk, ProjectDocument
from src.lib.chunker import chunk_text
from src.lib.embedder import Embedder
from src.lib.file_parsers import parse_file


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

    async def upload_file(
        self,
        project_id: uuid.UUID,
        project_slug: str,
        filename: str,
        file_bytes: bytes,
    ) -> ProjectDocument:
        """Upload a binary file (PDF, Word, Excel, CSV, etc.).

        Parses the file to extract text, stores the original file,
        and indexes the content for vector search.
        """
        content = parse_file(file_bytes, filename)
        ext = Path(filename).suffix.lower()

        # Determine doc_type from extension
        doc_type_map = {
            ".pdf": "pdf",
            ".docx": "word",
            ".xlsx": "excel",
            ".xls": "excel",
            ".csv": "csv",
            ".md": "markdown",
            ".txt": "text",
        }
        doc_type = doc_type_map.get(ext, "text")

        # Store original file to filesystem
        storage_dir = Path("data/knowledge") / project_slug
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / filename
        file_path.write_bytes(file_bytes)

        return await self.upload(
            project_id=project_id,
            filename=filename,
            content=content,
            doc_type=doc_type,
        )

    async def list_by_project(self, project_id: uuid.UUID) -> list[ProjectDocument]:
        result = await self.session.execute(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
            .order_by(ProjectDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, document_id: uuid.UUID, project_slug: str | None = None) -> None:
        doc = await self.session.get(ProjectDocument, document_id)
        if not doc:
            raise ValueError("Document not found")

        # Remove file from filesystem if it exists
        if project_slug:
            file_path = Path("data/knowledge") / project_slug / doc.filename
            if file_path.exists():
                os.remove(file_path)

        await self.session.delete(doc)
        await self.session.commit()
