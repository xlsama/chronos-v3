import json
import re

import httpx

from src.lib.logger import logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult


def _parse_es_command(command: str) -> tuple[str, str, dict | None]:
    """Parse an Elasticsearch command string.

    Format: "METHOD /path [json_body]"
    Examples:
        GET /_cat/indices?v
        POST /my_index/_search {"query": {"match_all": {}}}
    """
    cmd = command.strip()
    # Match: METHOD /path [optional body]
    m = re.match(r"^(GET|POST|PUT|DELETE|HEAD)\s+(\S+)(.*)", cmd, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError(f"无法解析命令，格式: METHOD /path [json_body]\n示例: GET /_cat/indices?v")

    method = m.group(1).upper()
    path = m.group(2)
    body_str = m.group(3).strip()

    body = None
    if body_str:
        body = json.loads(body_str)

    return method, path, body


class ElasticsearchConnector(ServiceConnector):
    service_type = "elasticsearch"

    def __init__(
        self,
        host: str,
        port: int,
        use_tls: bool = False,
        username: str | None = None,
        password: str | None = None,
    ):
        scheme = "https" if use_tls else "http"
        self._base_url = f"{scheme}://{host}:{port}"
        self._auth = (username, password) if username and password else None

    async def execute(self, command: str) -> ServiceResult:
        method, path, body = _parse_es_command(command)
        url = f"{self._base_url}{path}"
        body_preview = str(body)[:200] if body else ""
        logger.info(f"[elasticsearch] Executing: {method} {path} {body_preview}")

        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            kwargs: dict = {}
            if self._auth:
                kwargs["auth"] = self._auth
            if body is not None:
                kwargs["json"] = body

            resp = await client.request(method, url, **kwargs)

        if resp.status_code >= 400:
            logger.info(f"[elasticsearch] Error: HTTP {resp.status_code}")
            return ServiceResult(
                success=False,
                output="",
                error=f"HTTP {resp.status_code}: {resp.text[:1000]}",
            )

        # Try to format as pretty JSON, fall back to raw text
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            try:
                output = json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except Exception:
                output = resp.text
        else:
            output = resp.text

        logger.info(f"[elasticsearch] Result: HTTP {resp.status_code}, {len(output)} chars")
        return ServiceResult(success=True, output=output)

    async def close(self) -> None:
        pass  # httpx client is created per-request
