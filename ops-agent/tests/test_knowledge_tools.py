"""Tests for knowledge tools — mock Embedder + VectorStore + Reranker."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lib.reranker import RerankResult
from src.tools.knowledge_tools import _format_source, search_knowledge_base


class TestFormatSource:
    def test_plain_filename(self):
        assert _format_source("readme.md", {}) == "readme.md"

    def test_with_page(self):
        assert _format_source("report.pdf", {"page": 3}) == "report.pdf, 第3页"

    def test_with_slide(self):
        assert _format_source("deck.pptx", {"slide": 5}) == "deck.pptx, 第5张幻灯片"

    def test_with_sheet(self):
        assert _format_source("data.xlsx", {"sheet": "Sales"}) == "data.xlsx, 工作表: Sales"

    def test_image_tag(self):
        assert _format_source("arch.png", {"source_type": "image"}) == "arch.png [图片]"

    def test_page_and_image(self):
        result = _format_source("scan.pdf", {"page": 1, "source_type": "image"})
        assert "第1页" in result
        assert "[图片]" in result


class TestSearchKnowledgeBase:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    async def test_returns_formatted_results_with_metadata(self, mock_session):
        project_id = str(uuid.uuid4())

        mock_project = MagicMock()
        mock_project.service_md = "# Service Architecture\nUsing AWS."

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
            patch("src.tools.knowledge_tools.Reranker") as mock_rr_cls,
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = mock_project

            # Mock infra query to return empty
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            mock_emb = AsyncMock()
            mock_emb.embed_text.return_value = [0.1] * 1024
            mock_emb_cls.return_value = mock_emb

            mock_vs = AsyncMock()
            mock_vs.search.return_value = [
                {"content": "chunk 1", "filename": "report.pdf", "distance": 0.1,
                 "chunk_index": 0, "id": "1", "document_id": "d1", "metadata": {"page": 3}},
                {"content": "chunk 2", "filename": "deck.pptx", "distance": 0.2,
                 "chunk_index": 1, "id": "2", "document_id": "d2", "metadata": {"slide": 5}},
            ]
            mock_vs_cls.return_value = mock_vs

            mock_rr = AsyncMock()
            mock_rr.rerank.return_value = [
                RerankResult(index=0, relevance_score=0.95),
                RerankResult(index=1, relevance_score=0.80),
            ]
            mock_rr_cls.return_value = mock_rr

            result = await search_knowledge_base(query="how to deploy", project_id=project_id)

        assert "Service Architecture" in result
        assert "chunk 1" in result
        assert "chunk 2" in result
        assert "report.pdf, 第3页" in result
        assert "deck.pptx, 第5张幻灯片" in result
        assert "0.95" in result

    async def test_no_results(self, mock_session):
        project_id = str(uuid.uuid4())

        mock_project = MagicMock()
        mock_project.service_md = None

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
            patch("src.tools.knowledge_tools.Reranker") as mock_rr_cls,
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = mock_project

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            mock_emb = AsyncMock()
            mock_emb.embed_text.return_value = [0.1] * 1024
            mock_emb_cls.return_value = mock_emb

            mock_vs = AsyncMock()
            mock_vs.search.return_value = []
            mock_vs_cls.return_value = mock_vs

            result = await search_knowledge_base(query="anything", project_id=project_id)

        assert "没有找到" in result or "No relevant" in result or result != ""
        mock_rr_cls.return_value.rerank.assert_not_called()

    async def test_project_not_found(self, mock_session):
        project_id = str(uuid.uuid4())

        with patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = None

            result = await search_knowledge_base(query="test", project_id=project_id)

        assert "未找到项目" in result or "not found" in result.lower()

    async def test_includes_service_md_when_present(self, mock_session):
        project_id = str(uuid.uuid4())

        mock_project = MagicMock()
        mock_project.service_md = "# My Service Setup\nVery important info."

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
            patch("src.tools.knowledge_tools.Reranker"),
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = mock_project

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            mock_emb = AsyncMock()
            mock_emb.embed_text.return_value = [0.1] * 1024
            mock_emb_cls.return_value = mock_emb

            mock_vs = AsyncMock()
            mock_vs.search.return_value = []
            mock_vs_cls.return_value = mock_vs

            result = await search_knowledge_base(query="service", project_id=project_id)

        assert "My Service Setup" in result

    async def test_includes_infrastructure_data(self, mock_session):
        """search_knowledge_base includes infrastructure + services in results."""
        project_id = str(uuid.uuid4())

        mock_project = MagicMock()
        mock_project.service_md = None

        # Mock infrastructure with services
        mock_svc = MagicMock()
        mock_svc.name = "nginx"
        mock_svc.status = "running"
        mock_svc.port = 80
        mock_svc.namespace = None

        mock_conn = MagicMock()
        mock_conn.name = "prod-web-01"
        mock_conn.type = "ssh"
        mock_conn.id = uuid.uuid4()
        mock_conn.status = "online"
        mock_conn.host = "10.0.0.1"
        mock_conn.port = 22
        mock_conn.services = [mock_svc]

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
            patch("src.tools.knowledge_tools.Reranker"),
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = mock_project

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_conn]
            mock_session.execute.return_value = mock_result

            mock_emb = AsyncMock()
            mock_emb.embed_text.return_value = [0.1] * 1024
            mock_emb_cls.return_value = mock_emb

            mock_vs = AsyncMock()
            mock_vs.search.return_value = []
            mock_vs_cls.return_value = mock_vs

            result = await search_knowledge_base(query="nginx", project_id=project_id)

        assert "prod-web-01" in result
        assert "nginx" in result
        assert "关联连接" in result
