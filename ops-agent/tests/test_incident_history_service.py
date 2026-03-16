"""Tests for IncidentHistoryService.search — over-fetch + rerank logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lib.reranker import RerankResult
from src.services.incident_history_service import IncidentHistoryService


class TestIncidentHistoryServiceSearch:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_embedder(self):
        emb = AsyncMock()
        emb.embed_text.return_value = [0.1] * 1024
        return emb

    @pytest.fixture
    def mock_reranker(self):
        return AsyncMock()

    async def test_search_overfetches_and_reranks(self, mock_session, mock_embedder, mock_reranker):
        """search() fetches limit*4 candidates then reranks to top limit."""
        # Simulate DB returning 8 rows (limit=2, overfetch=8)
        mock_rows = [
            MagicMock(title=f"Incident {i}", summary_md=f"Summary {i}", distance=0.1 * i)
            for i in range(8)
        ]
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        mock_reranker.rerank.return_value = [
            RerankResult(index=3, relevance_score=0.95),
            RerankResult(index=1, relevance_score=0.80),
        ]

        service = IncidentHistoryService(
            session=mock_session, embedder=mock_embedder, reranker=mock_reranker
        )
        results = await service.search(query="disk full", limit=2)

        assert len(results) == 2
        assert results[0]["title"] == "Incident 3"
        assert results[0]["relevance_score"] == 0.95
        assert results[1]["title"] == "Incident 1"
        assert results[1]["relevance_score"] == 0.80

        # Verify reranker was called with all 8 candidate summaries
        mock_reranker.rerank.assert_called_once()
        call_args = mock_reranker.rerank.call_args
        assert len(call_args.kwargs["documents"]) == 8
        assert call_args.kwargs["top_n"] == 2

    async def test_search_empty_results_skips_rerank(self, mock_session, mock_embedder, mock_reranker):
        """search() with no DB results returns empty without calling reranker."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        service = IncidentHistoryService(
            session=mock_session, embedder=mock_embedder, reranker=mock_reranker
        )
        results = await service.search(query="unknown", limit=5)

        assert results == []
        mock_reranker.rerank.assert_not_called()

    async def test_search_preserves_original_fields(self, mock_session, mock_embedder, mock_reranker):
        """Reranked results preserve title, summary_md, distance from original candidates."""
        mock_rows = [
            MagicMock(title="Event A", summary_md="Details A", distance=0.05),
            MagicMock(title="Event B", summary_md="Details B", distance=0.10),
        ]
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        mock_reranker.rerank.return_value = [
            RerankResult(index=1, relevance_score=0.99),
        ]

        service = IncidentHistoryService(
            session=mock_session, embedder=mock_embedder, reranker=mock_reranker
        )
        results = await service.search(query="event", limit=1)

        assert len(results) == 1
        assert results[0]["title"] == "Event B"
        assert results[0]["summary_md"] == "Details B"
        assert results[0]["distance"] == 0.10
        assert results[0]["relevance_score"] == 0.99
