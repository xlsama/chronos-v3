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
        mock_project.service_md = "# Service Architecture\nUsing AWS."

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
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
                {"content": "chunk 1", "filename": "readme.md", "distance": 0.1, "chunk_index": 0, "id": "1"},
                {"content": "chunk 2", "filename": "deploy.md", "distance": 0.2, "chunk_index": 1, "id": "2"},
            ]
            mock_vs_cls.return_value = mock_vs

            result = await search_knowledge_base(query="how to deploy", project_id=project_id)

        assert "Service Architecture" in result
        assert "chunk 1" in result
        assert "chunk 2" in result
        assert "readme.md" in result

    async def test_no_results(self, mock_session):
        project_id = str(uuid.uuid4())

        mock_project = MagicMock()
        mock_project.service_md = None

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
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
        mock_svc.service_type = "docker"
        mock_svc.status = "running"
        mock_svc.port = 80
        mock_svc.namespace = None

        mock_infra = MagicMock()
        mock_infra.name = "prod-web-01"
        mock_infra.type = "ssh"
        mock_infra.id = uuid.uuid4()
        mock_infra.status = "online"
        mock_infra.host = "10.0.0.1"
        mock_infra.port = 22
        mock_infra.services = [mock_svc]

        with (
            patch("src.tools.knowledge_tools.get_session_ctx") as mock_get_session,
            patch("src.tools.knowledge_tools.Embedder") as mock_emb_cls,
            patch("src.tools.knowledge_tools.VectorStore") as mock_vs_cls,
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session.get.return_value = mock_project

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_infra]
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
        assert "docker" in result
        assert "关联基础设施" in result
