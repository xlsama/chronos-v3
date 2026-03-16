import httpx

from src.lib.logger import logger


class PrometheusConnector:
    def __init__(self, endpoint: str, headers: dict[str, str] | None = None, timeout: int = 30):
        self.endpoint = endpoint.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    async def query_instant(self, query: str) -> dict:
        """Execute an instant PromQL query."""
        url = f"{self.endpoint}/api/v1/query"
        params = {"query": query}
        return await self._get(url, params)

    async def query_range(
        self, query: str, start: str, end: str, step: str = "60s"
    ) -> dict:
        """Execute a range PromQL query."""
        url = f"{self.endpoint}/api/v1/query_range"
        params = {"query": query, "start": start, "end": end, "step": step}
        return await self._get(url, params)

    async def test_connection(self) -> bool:
        try:
            url = f"{self.endpoint}/api/v1/status/buildinfo"
            result = await self._get(url, {})
            return result.get("status") == "success"
        except Exception as e:
            logger.warning(f"Prometheus connection test failed: {e}")
            return False

    async def _get(self, url: str, params: dict) -> dict:
        logger.info(f"Prometheus query: {url} params={params}")
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            return response.json()
