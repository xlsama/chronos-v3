from dataclasses import dataclass

import httpx

from src.env import get_settings


@dataclass
class RerankResult:
    index: int
    relevance_score: float


class Reranker:
    def __init__(self):
        s = get_settings()
        self.api_key = s.dashscope_api_key
        self.base_url = s.rerank_base_url
        self.model = s.rerank_model

    async def rerank(
        self, query: str, documents: list[str], top_n: int = 5
    ) -> list[RerankResult]:
        if not documents or len(documents) <= top_n:
            return [
                RerankResult(index=i, relevance_score=1.0)
                for i in range(len(documents))
            ]

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/reranks",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_n,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            RerankResult(index=r["index"], relevance_score=r["relevance_score"])
            for r in data["results"]
        ]
