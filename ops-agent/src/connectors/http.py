from dataclasses import dataclass

import httpx

from src.lib.logger import logger


@dataclass
class HTTPResult:
    status_code: int
    body: str
    headers: dict[str, str]


class HTTPConnector:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
    ) -> HTTPResult:
        logger.info(f"HTTP {method} {url}")
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                content=body,
            )
            return HTTPResult(
                status_code=response.status_code,
                body=response.text[:10000],  # Truncate large responses
                headers=dict(response.headers),
            )
