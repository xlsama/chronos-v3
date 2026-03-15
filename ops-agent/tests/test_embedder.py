"""Tests for Embedder — mock OpenAI client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lib.embedder import Embedder


class TestEmbedder:
    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        return client

    @pytest.fixture
    def embedder(self, mock_client):
        with patch("src.lib.embedder.AsyncOpenAI", return_value=mock_client):
            emb = Embedder()
            emb.client = mock_client
            return emb

    def _make_embedding_response(self, vectors: list[list[float]]):
        resp = MagicMock()
        resp.data = [MagicMock(embedding=v) for v in vectors]
        return resp

    async def test_embed_text_single(self, embedder, mock_client):
        vec = [0.1] * 1024
        mock_client.embeddings.create.return_value = self._make_embedding_response([vec])

        result = await embedder.embed_text("hello")

        assert result == vec
        mock_client.embeddings.create.assert_called_once()
        call_kwargs = mock_client.embeddings.create.call_args.kwargs
        assert call_kwargs["input"] == ["hello"]

    async def test_embed_texts_batch(self, embedder, mock_client):
        vecs = [[0.1] * 1024, [0.2] * 1024]
        mock_client.embeddings.create.return_value = self._make_embedding_response(vecs)

        result = await embedder.embed_texts(["hello", "world"])

        assert len(result) == 2
        assert result[0] == vecs[0]
        assert result[1] == vecs[1]

    async def test_embed_texts_splits_batches(self, embedder, mock_client):
        vec = [0.1] * 1024

        def side_effect(**kwargs):
            n = len(kwargs["input"])
            return self._make_embedding_response([vec] * n)

        mock_client.embeddings.create.side_effect = side_effect

        texts = [f"text_{i}" for i in range(25)]
        result = await embedder.embed_texts(texts, batch_size=10)

        assert len(result) == 25
        assert mock_client.embeddings.create.call_count == 3  # 10 + 10 + 5

    async def test_embed_texts_empty_raises(self, embedder):
        with pytest.raises(ValueError, match="empty"):
            await embedder.embed_texts([])

    async def test_embed_texts_passes_model(self, embedder, mock_client):
        vec = [0.1] * 1024
        mock_client.embeddings.create.return_value = self._make_embedding_response([vec])

        await embedder.embed_text("test")

        call_kwargs = mock_client.embeddings.create.call_args.kwargs
        assert "model" in call_kwargs
