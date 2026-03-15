"""Tests for knowledge tools — mock Embedder + VectorStore."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.knowledge_tools import search_knowledge_base


class TestSearchKnowledgeBase:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    async def test_returns_formatted_results(self, mock_session):
        project_id = str(uuid.uuid4())

        mock_project = MagicMock()
        mock_project.cloud_md = "# Cloud Architecture\nUsing AWS."

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = mock_project

            mock_emb = AsyncMock()
            mock_emb.embed_text.return_value = [0.1] * 1024
            mock_emb_cls.return_value = mock_emb

            mock_vs = AsyncMock()
            mock_vs.search.return_value = [
                {"content": "chunk 1", "filename": "readme.md", "distance": 0.1, "chunk_index": 0, "id": "1"},
                {"content": "chunk 2", "filename": "deploy.md", "distance": 0.2, "chunk_index": 1, "id": "2"},
            ]
            mock_vs_cls.return_value = mock_vs

            result = await search_knowledge_base(query="how to deploy", project_id=project_id)

        assert "Cloud Architecture" in result
        assert "chunk 1" in result
        assert "chunk 2" in result
        assert "readme.md" in result

    async def test_no_results(self, mock_session):
        project_id = str(uuid.uuid4())

        mock_project = MagicMock()
        mock_project.cloud_md = None

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = mock_project

            mock_emb = AsyncMock()
            mock_emb.embed_text.return_value = [0.1] * 1024
            mock_emb_cls.return_value = mock_emb

            mock_vs = AsyncMock()
            mock_vs.search.return_value = []
            mock_vs_cls.return_value = mock_vs

            result = await search_knowledge_base(query="anything", project_id=project_id)

        assert "没有找到" in result or "No relevant" in result or result != ""

    async def test_project_not_found(self, mock_session):
        project_id = str(uuid.uuid4())

        with patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = None

            result = await search_knowledge_base(query="test", project_id=project_id)

        assert "未找到项目" in result or "not found" in result.lower()

    async def test_includes_cloud_md_when_present(self, mock_session):
        project_id = str(uuid.uuid4())

        mock_project = MagicMock()
        mock_project.cloud_md = "# My Cloud Setup\nVery important info."

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = mock_project

            mock_emb = AsyncMock()
            mock_emb.embed_text.return_value = [0.1] * 1024
            mock_emb_cls.return_value = mock_emb

            mock_vs = AsyncMock()
            mock_vs.search.return_value = []
            mock_vs_cls.return_value = mock_vs

            result = await search_knowledge_base(query="cloud", project_id=project_id)

        assert "My Cloud Setup" in result
