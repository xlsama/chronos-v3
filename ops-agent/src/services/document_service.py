from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DocumentChunk, ProjectDocument
from src.lib.chunker import ChunkWithMetadata, chunk_segments, chunk_text
from src.lib.embedder import Embedder
from src.lib.file_parsers import ParsedSegment, is_image, parse_file_segments

if TYPE_CHECKING:
    from src.lib.image_describer import ImageDescriber


class DocumentService:
    def __init__(self, session: AsyncSession, embedder: Embedder, image_describer: ImageDescriber | None = None):
        self.session = session
        self.embedder = embedder
        self.image_describer = image_describer

    async def upload(
        self,
        project_id: uuid.UUID,
        filename: str,
        content: str,
        doc_type: str,
        segments: list[ParsedSegment] | None = None,
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

        if segments:
            chunks_with_meta = chunk_segments(segments)
        else:
            chunks_with_meta = [ChunkWithMetadata(content=c, metadata={}) for c in chunk_text(content)]

        texts = [c.content for c in chunks_with_meta]
        embeddings = await self.embedder.embed_texts(texts)

        chunk_models = [
            DocumentChunk(
                document_id=doc.id,
                project_id=project_id,
                chunk_index=i,
                content=c.content,
                embedding=emb,
                chunk_metadata=c.metadata,
            )
            for i, (c, emb) in enumerate(zip(chunks_with_meta, embeddings))
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
        """Upload a binary file (PDF, Word, Excel, CSV, image, etc.).

        Parses the file to extract text, stores the original file,
        and indexes the content for vector search.
        """
        ext = Path(filename).suffix.lower()

        # Store original file to filesystem
        storage_dir = Path("data/knowledge") / project_slug
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / filename
        file_path.write_bytes(file_bytes)

        if is_image(filename):
            if not self.image_describer:
                raise ValueError("Image upload requires an ImageDescriber instance")
            description = await self.image_describer.describe(file_bytes, filename)
            content = description
            doc_type = "image"
            segments = [ParsedSegment(content=description, metadata={"source_type": "image"})]
        else:
            segments = parse_file_segments(file_bytes, filename)
            content = "\n\n".join(seg.content for seg in segments)
            doc_type_map = {
                ".pdf": "pdf",
                ".docx": "word",
                ".xlsx": "excel",
                ".xls": "excel",
                ".csv": "csv",
                ".md": "markdown",
                ".txt": "text",
                ".pptx": "pptx",
                ".html": "html",
                ".htm": "html",
                ".json": "json",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".log": "log",
            }
            doc_type = doc_type_map.get(ext, "text")

        return await self.upload(
            project_id=project_id,
            filename=filename,
            content=content,
            doc_type=doc_type,
            segments=segments,
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
