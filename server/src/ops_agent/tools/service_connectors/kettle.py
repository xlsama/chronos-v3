import json
import re
import xml.etree.ElementTree as ET

import httpx

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult

log = get_logger(component="service_exec")


def _parse_http_command(command: str) -> tuple[str, str, dict | None]:
    """Parse an HTTP command string.

    Format: "METHOD /path [json_body]"
    Examples:
        GET /kettle/status
        GET /kettle/transStatus/?name=my_trans
    """
    cmd = command.strip()
    m = re.match(r"^(GET|POST|PUT|DELETE|HEAD)\s+(\S+)(.*)", cmd, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("无法解析命令，格式: METHOD /path\n示例: GET /kettle/status")

    method = m.group(1).upper()
    path = m.group(2)
    body_str = m.group(3).strip()

    body = None
    if body_str:
        body = json.loads(body_str)

    return method, path, body


def _xml_to_text(xml_str: str) -> str:
    """Convert XML response to human-readable text."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return xml_str

    lines: list[str] = []

    def _walk(elem: ET.Element, indent: int = 0) -> None:
        tag = elem.tag
        text = (elem.text or "").strip()
        prefix = "  " * indent
        if text:
            lines.append(f"{prefix}{tag}: {text}")
        elif len(elem) == 0:
            lines.append(f"{prefix}{tag}: (empty)")
        else:
            lines.append(f"{prefix}{tag}:")
        for child in elem:
            _walk(child, indent + 1)

    _walk(root)
    return "\n".join(lines)


class KettleConnector(ServiceConnector):
    service_type = "kettle"

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
        method, path, body = _parse_http_command(command)
        url = f"{self._base_url}{path}"
        log.info("Executing", method=method, path=path)

        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            kwargs: dict = {}
            if self._auth:
                kwargs["auth"] = self._auth
            if body is not None:
                kwargs["json"] = body

            resp = await client.request(method, url, **kwargs)

        if resp.status_code >= 400:
            log.info("Error", status_code=resp.status_code)
            return ServiceResult(
                success=False,
                output="",
                error=f"HTTP {resp.status_code}: {resp.text[:1000]}",
            )

        content_type = resp.headers.get("content-type", "")
        if "xml" in content_type:
            output = _xml_to_text(resp.text)
        elif "json" in content_type:
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
