from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_session_factory
from src.db.models import DocumentChunk, ProjectDocument
from src.lib.chunker import ChunkWithMetadata, chunk_segments, chunk_text
from src.lib.embedder import Embedder
from src.lib.file_parsers import ParsedSegment, is_image, parse_file_segments
from src.lib.logger import get_logger
from src.lib.paths import knowledge_dir

if TYPE_CHECKING:
    from src.lib.image_describer import ImageDescriber

log = get_logger()


async def _index_document_background(
    document_id: uuid.UUID,
    project_id: uuid.UUID,
    content: str,
    segments: list[ParsedSegment] | None,
) -> None:
    """Background task: chunk, embed, and save vectors for a document."""
    factory = get_session_factory()
    embedder = Embedder()
    async with factory() as session:
        try:
            doc = await session.get(ProjectDocument, document_id)
            if not doc:
                log.error("Document not found for indexing", document_id=str(document_id))
                return

            # Skip indexing if content is empty
            if (not content or not content.strip()) and not segments:
                doc.status = "indexed"
                await session.commit()
                log.info("Document has no content, skipped indexing", document_id=str(document_id))
                return

            doc.status = "indexing"
            await session.commit()

            # Delete old chunks (no-op for new documents)
            old_chunks = await session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
            for chunk in old_chunks.scalars().all():
                await session.delete(chunk)
            await session.flush()

            if segments:
                chunks_with_meta = chunk_segments(segments)
            else:
                chunks_with_meta = [
                    ChunkWithMetadata(content=c, metadata={}) for c in chunk_text(content)
                ]

            texts = [c.content for c in chunks_with_meta]
            embeddings = await embedder.embed_texts(texts)

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
            session.add_all(chunk_models)

            doc.status = "indexed"
            doc.error_message = None
            await session.commit()
            log.info(
                "Document indexed successfully",
                document_id=str(document_id),
                chunks=len(chunk_models),
            )
        except Exception as e:
            await session.rollback()
            async with factory() as err_session:
                doc = await err_session.get(ProjectDocument, document_id)
                if doc:
                    doc.status = "index_failed"
                    doc.error_message = str(e)[:500]
                    await err_session.commit()
            log.error("Failed to index document", document_id=str(document_id), error=str(e))


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        embedder: Embedder,
        image_describer: ImageDescriber | None = None,
    ):
        self.session = session
        self.embedder = embedder
        self.image_describer = image_describer

    async def save_document(
        self,
        project_id: uuid.UUID,
        filename: str,
        content: str,
        doc_type: str,
        status: str = "pending",
    ) -> ProjectDocument:
        """Phase 1: Save document record. Returns immediately."""
        doc = ProjectDocument(
            project_id=project_id,
            filename=filename,
            content=content,
            doc_type=doc_type,
            status=status,
        )
        self.session.add(doc)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

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
            chunks_with_meta = [
                ChunkWithMetadata(content=c, metadata={}) for c in chunk_text(content)
            ]

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

        doc.status = "indexed"
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
        storage_dir = knowledge_dir(project_slug)
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

    async def get(self, document_id: uuid.UUID) -> ProjectDocument | None:
        return await self.session.get(ProjectDocument, document_id)

    async def update(
        self,
        document_id: uuid.UUID,
        content: str,
        project_slug: str,
    ) -> ProjectDocument:
        doc = await self.session.get(ProjectDocument, document_id)
        if not doc:
            raise ValueError("Document not found")

        doc.content = content

        # Sync to disk
        file_path = knowledge_dir(project_slug) / doc.filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        # agents_config documents: only update content, skip chunk + embed
        if doc.doc_type == "agents_config":
            doc.status = "indexed"
        else:
            doc.status = "pending"

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

    async def delete(self, document_id: uuid.UUID, project_slug: str | None = None) -> None:
        doc = await self.session.get(ProjectDocument, document_id)
        if not doc:
            raise ValueError("Document not found")
        if doc.doc_type == "agents_config":
            raise ValueError("Cannot delete agents_config document")

        # Remove file from filesystem if it exists
        if project_slug:
            file_path = knowledge_dir(project_slug) / doc.filename
            if file_path.exists():
                os.remove(file_path)

        await self.session.delete(doc)
        await self.session.commit()
