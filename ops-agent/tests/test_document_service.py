"""Tests for DocumentService — upload, list, delete."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lib.file_parsers import ParsedSegment
from src.services.document_service import DocumentService


class TestDocumentService:
    @pytest.fixture
    def session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.add_all = MagicMock()
        return session

    @pytest.fixture
    def embedder(self):
        emb = AsyncMock()
        emb.embed_texts = AsyncMock(return_value=[[0.1] * 1024, [0.2] * 1024])
        return emb

    @pytest.fixture
    def service(self, session, embedder):
        return DocumentService(session=session, embedder=embedder)

    @patch("src.services.document_service.chunk_text", return_value=["chunk 1", "chunk 2"])
    async def test_upload_creates_document(self, mock_chunk, service, session):
        project_id = uuid.uuid4()

        result = await service.upload(
            project_id=project_id,
            filename="readme.md",
            content="# Hello\n\nWorld",
            doc_type="markdown",
        )

        assert result.filename == "readme.md"
        assert result.project_id == project_id
        assert result.status == "ready"
        session.add.assert_called()  # document added
        session.commit.assert_called()

    @patch("src.services.document_service.chunk_text", return_value=["chunk 1", "chunk 2"])
    async def test_upload_calls_chunker(self, mock_chunk, service, session):
        await service.upload(
            project_id=uuid.uuid4(),
            filename="test.md",
            content="some content",
            doc_type="markdown",
        )

        mock_chunk.assert_called_once_with("some content")

    @patch("src.services.document_service.chunk_text", return_value=["chunk 1", "chunk 2"])
    async def test_upload_calls_embedder(self, mock_chunk, service, session, embedder):
        await service.upload(
            project_id=uuid.uuid4(),
            filename="test.md",
            content="some content",
            doc_type="markdown",
        )

        embedder.embed_texts.assert_called_once_with(["chunk 1", "chunk 2"])

    @patch("src.services.document_service.chunk_text", return_value=["chunk 1", "chunk 2"])
    async def test_upload_creates_chunks(self, mock_chunk, service, session):
        await service.upload(
            project_id=uuid.uuid4(),
            filename="test.md",
            content="some content",
            doc_type="markdown",
        )

        session.add_all.assert_called_once()
        chunks = session.add_all.call_args[0][0]
        assert len(chunks) == 2
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1

    async def test_upload_passes_metadata_to_chunks(self, session, embedder):
        embedder.embed_texts = AsyncMock(return_value=[[0.1] * 1024, [0.2] * 1024])
        service = DocumentService(session=session, embedder=embedder)

        segments = [
            ParsedSegment(content="Page one text", metadata={"page": 1}),
            ParsedSegment(content="Page two text", metadata={"page": 2}),
        ]

        await service.upload(
            project_id=uuid.uuid4(),
            filename="report.pdf",
            content="Page one text\n\nPage two text",
            doc_type="pdf",
            segments=segments,
        )

        session.add_all.assert_called_once()
        chunks = session.add_all.call_args[0][0]
        assert len(chunks) == 2
        assert chunks[0].chunk_metadata == {"page": 1}
        assert chunks[1].chunk_metadata == {"page": 2}

    async def test_upload_file_image(self, session, embedder):
        embedder.embed_texts = AsyncMock(return_value=[[0.1] * 1024])
        image_describer = AsyncMock()
        image_describer.describe = AsyncMock(return_value="A server rack in a datacenter")

        service = DocumentService(session=session, embedder=embedder, image_describer=image_describer)

        with patch("src.services.document_service.Path") as mock_path_cls:
            mock_path_instance = MagicMock()
            mock_path_cls.return_value = mock_path_instance
            mock_path_instance.suffix = ".png"
            mock_path_instance.__truediv__ = MagicMock(return_value=mock_path_instance)
            mock_path_instance.mkdir = MagicMock()
            mock_path_instance.write_bytes = MagicMock()

            result = await service.upload_file(
                project_id=uuid.uuid4(),
                project_slug="my-project",
                filename="server.png",
                file_bytes=b"\x89PNG\r\n",
            )

        image_describer.describe.assert_called_once_with(b"\x89PNG\r\n", "server.png")
        assert result.doc_type == "image"

    async def test_list_by_project(self, service, session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        result = await service.list_by_project(uuid.uuid4())

        assert result == []

    async def test_delete_document(self, service, session):
        doc_id = uuid.uuid4()
        mock_doc = MagicMock()
        session.get.return_value = mock_doc

        await service.delete(doc_id)

        session.delete.assert_called_once_with(mock_doc)
        session.commit.assert_called_once()

    async def test_delete_not_found_raises(self, service, session):
        session.get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.delete(uuid.uuid4())
