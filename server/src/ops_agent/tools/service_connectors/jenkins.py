import json
import re

import httpx

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult

log = get_logger(component="service_exec")


def _parse_http_command(command: str) -> tuple[str, str, dict | None]:
    """Parse an HTTP command string.

    Format: "METHOD /path [json_body]"
    Examples:
        GET /api/json
        POST /job/my-job/build
    """
    cmd = command.strip()
    m = re.match(r"^(GET|POST|PUT|DELETE|HEAD)\s+(\S+)(.*)", cmd, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("无法解析命令，格式: METHOD /path [json_body]\n示例: GET /api/json")

    method = m.group(1).upper()
    path = m.group(2)
    body_str = m.group(3).strip()

    body = None
    if body_str:
        body = json.loads(body_str)

    return method, path, body


class JenkinsConnector(ServiceConnector):
    service_type = "jenkins"

    def __init__(
        self,
        host: str,
        port: int,
        use_tls: bool = False,
        path: str = "",
        username: str | None = None,
        password: str | None = None,
    ):
        scheme = "https" if use_tls else "http"
        base_path = path.rstrip("/") if path else ""
        self._base_url = f"{scheme}://{host}:{port}{base_path}"
        self._auth = (username, password) if username and password else None
        self._crumb: tuple[str, str] | None = None

    async def _fetch_crumb(self, client: httpx.AsyncClient) -> tuple[str, str] | None:
        """Fetch Jenkins CSRF crumb for POST requests."""
        if self._crumb is not None:
            return self._crumb
        try:
            kwargs: dict = {}
            if self._auth:
                kwargs["auth"] = self._auth
            resp = await client.get(
                f"{self._base_url}/crumbIssuer/api/json", **kwargs
            )
            if resp.status_code == 200:
                data = resp.json()
                self._crumb = (data["crumbRequestField"], data["crumb"])
                return self._crumb
        except Exception:
            pass
        return None

    async def execute(self, command: str) -> ServiceResult:
        method, path, body = _parse_http_command(command)
        url = f"{self._base_url}{path}"
        log.info("Executing", method=method, path=path)

        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            kwargs: dict = {}
            if self._auth:
                kwargs["auth"] = self._auth
            if body is not None:
                kwargs["json"] = body

            # POST/PUT/DELETE need CSRF crumb
            if method in ("POST", "PUT", "DELETE"):
                crumb = await self._fetch_crumb(client)
                if crumb:
                    kwargs.setdefault("headers", {})[crumb[0]] = crumb[1]

            resp = await client.request(method, url, **kwargs)

        if resp.status_code >= 400:
            log.info("Error", status_code=resp.status_code)
            return ServiceResult(
                success=False,
                output="",
                error=f"HTTP {resp.status_code}: {resp.text[:1000]}",
            )

        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            try:
                output = json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except Exception:
                output = resp.text
        else:
            output = resp.text

        log.info("Result", status_code=resp.status_code, output_len=len(output))
        return ServiceResult(success=True, output=output)

    async def close(self) -> None:
        pass
