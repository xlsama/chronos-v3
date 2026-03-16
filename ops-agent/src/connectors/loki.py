import httpx

from src.lib.logger import logger


class LokiConnector:
    def __init__(self, endpoint: str, headers: dict[str, str] | None = None, timeout: int = 30):
        self.endpoint = endpoint.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    async def query_range(
        self,
        query: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Execute a LogQL range query."""
        url = f"{self.endpoint}/loki/api/v1/query_range"
        params: dict = {"query": query, "limit": str(limit)}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return await self._get(url, params)

    async def test_connection(self) -> bool:
        try:
            url = f"{self.endpoint}/ready"
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(url, headers=self.headers)
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Loki connection test failed: {e}")
            return False

    async def _get(self, url: str, params: dict) -> dict:
        logger.info(f"Loki query: {url} params={params}")
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            return response.json()
