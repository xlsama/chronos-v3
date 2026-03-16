"""Tests for the Reranker class."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.lib.reranker import Reranker, RerankResult


class TestReranker:
    @pytest.fixture
    def reranker(self):
        with patch("src.lib.reranker.get_settings") as mock_settings:
            s = mock_settings.return_value
            s.dashscope_api_key = "test-key"
            s.rerank_base_url = "https://example.com/v1"
            s.rerank_model = "qwen3-rerank"
            yield Reranker()

    async def test_rerank_returns_ordered_results(self, reranker):
        mock_response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.com/v1/reranks"),
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.80},
                    {"index": 4, "relevance_score": 0.60},
                ]
            },
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            results = await reranker.rerank(
                query="disk full",
                documents=[f"doc {i}" for i in range(10)],
                top_n=3,
            )

        assert len(results) == 3
        assert results[0] == RerankResult(index=2, relevance_score=0.95)
        assert results[1] == RerankResult(index=0, relevance_score=0.80)
        assert results[2] == RerankResult(index=4, relevance_score=0.60)

    async def test_rerank_empty_documents(self, reranker):
        results = await reranker.rerank(query="test", documents=[], top_n=5)
        assert results == []

    async def test_rerank_skips_api_when_lte_top_n(self, reranker):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            results = await reranker.rerank(
                query="test",
                documents=["doc1", "doc2", "doc3"],
                top_n=5,
            )

        mock_post.assert_not_called()
        assert len(results) == 3
        assert all(r.relevance_score == 1.0 for r in results)
        assert [r.index for r in results] == [0, 1, 2]

    async def test_rerank_sends_correct_request(self, reranker):
        mock_response = httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.com/v1/reranks"),
            json={"results": [{"index": 0, "relevance_score": 0.9}]},
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await reranker.rerank(
                query="my query",
                documents=[f"doc {i}" for i in range(10)],
                top_n=1,
            )

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.args[0] == "https://example.com/v1/reranks"
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-key"
        body = call_kwargs.kwargs["json"]
        assert body["model"] == "qwen3-rerank"
        assert body["query"] == "my query"
        assert len(body["documents"]) == 10
        assert body["top_n"] == 1
