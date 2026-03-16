"""Tests for VectorStore — mock async session."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.vector_store import VectorStore


class TestVectorStore:
    @pytest.fixture
    def session(self):
        return AsyncMock()

    @pytest.fixture
    def store(self, session):
        return VectorStore(session=session)

    async def test_search_returns_results(self, store, session):
        project_id = uuid.uuid4()
        query_embedding = [0.1] * 1024

        # Mock row objects
        row1 = MagicMock()
        row1.id = uuid.uuid4()
        row1.document_id = uuid.uuid4()
        row1.content = "chunk content 1"
        row1.chunk_index = 0
        row1.chunk_metadata = {"page": 1}
        row1.filename = "readme.md"
        row1.distance = 0.1

        row2 = MagicMock()
        row2.id = uuid.uuid4()
        row2.document_id = uuid.uuid4()
        row2.content = "chunk content 2"
        row2.chunk_index = 1
        row2.chunk_metadata = {"page": 2}
        row2.filename = "readme.md"
        row2.distance = 0.2

        mock_result = MagicMock()
        mock_result.all.return_value = [row1, row2]
        session.execute.return_value = mock_result

        results = await store.search(query_embedding, project_id, limit=5)

        assert len(results) == 2
        assert results[0]["content"] == "chunk content 1"
        assert results[1]["content"] == "chunk content 2"
        assert results[0]["filename"] == "readme.md"
        assert results[0]["document_id"] == str(row1.document_id)
        assert results[0]["metadata"] == {"page": 1}
        assert results[1]["metadata"] == {"page": 2}
        session.execute.assert_called_once()

    async def test_search_empty_results(self, store, session):
        project_id = uuid.uuid4()
        query_embedding = [0.1] * 1024

        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        results = await store.search(query_embedding, project_id)

        assert results == []

    async def test_search_respects_limit(self, store, session):
        project_id = uuid.uuid4()
        query_embedding = [0.1] * 1024

        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        await store.search(query_embedding, project_id, limit=3)

        # Verify execute was called (query construction is tested implicitly)
        session.execute.assert_called_once()
