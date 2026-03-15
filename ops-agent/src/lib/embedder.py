from openai import AsyncOpenAI

from src.config import get_settings


class Embedder:
    def __init__(self):
        s = get_settings()
        self.client = AsyncOpenAI(api_key=s.dashscope_api_key, base_url=s.llm_base_url)
        self.model = s.embedding_model
        self.dimension = s.embedding_dimension

    async def embed_texts(self, texts: list[str], batch_size: int = 20) -> list[list[float]]:
        if not texts:
            raise ValueError("texts must not be empty")

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await self.client.embeddings.create(
                input=batch,
                model=self.model,
                dimensions=self.dimension,
            )
            all_embeddings.extend([d.embedding for d in resp.data])
        return all_embeddings

    async def embed_text(self, text: str) -> list[float]:
        result = await self.embed_texts([text])
        return result[0]
