import httpx

from src.lib.logger import logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult


def _format_prometheus_result(data: dict) -> str:
    """Format Prometheus query result."""
    result_type = data.get("resultType", "")
    results = data.get("result", [])

    if not results:
        return "(no data)"

    lines = []
    if result_type == "vector":
        for item in results:
            metric = item.get("metric", {})
            value = item.get("value", [])
            # metric{labels} = value @ timestamp
            metric_name = metric.pop("__name__", "")
            if metric:
                labels = ", ".join(f'{k}="{v}"' for k, v in metric.items())
                label_str = f"{{{labels}}}"
            else:
                label_str = ""
            ts = value[0] if len(value) > 0 else ""
            val = value[1] if len(value) > 1 else ""
            lines.append(f"{metric_name}{label_str} = {val} @ {ts}")
    elif result_type == "matrix":
        for item in results:
            metric = item.get("metric", {})
            values = item.get("values", [])
            metric_name = metric.pop("__name__", "")
            if metric:
                labels = ", ".join(f'{k}="{v}"' for k, v in metric.items())
                label_str = f"{{{labels}}}"
            else:
                label_str = ""
            lines.append(f"{metric_name}{label_str}:")
            for ts, val in values:
                lines.append(f"  {val} @ {ts}")
    elif result_type == "scalar":
        lines.append(str(results))
    else:
        lines.append(str(data))

    return "\n".join(lines)


class PrometheusConnector(ServiceConnector):
    service_type = "prometheus"

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

    async def execute(self, command: str) -> ServiceResult:
        """Execute a PromQL query."""
        expr = command.strip()
        url = f"{self._base_url}/api/v1/query"
        params = {"query": expr}
        logger.info(f"[prometheus] Executing PromQL: {expr[:200]}")

        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            kwargs: dict = {"params": params}
            if self._auth:
                kwargs["auth"] = self._auth
            resp = await client.get(url, **kwargs)

        if resp.status_code != 200:
            logger.info(f"[prometheus] Error: HTTP {resp.status_code}")
            return ServiceResult(
                success=False,
                output="",
                error=f"HTTP {resp.status_code}: {resp.text[:500]}",
            )

        body = resp.json()
        if body.get("status") != "success":
            return ServiceResult(
                success=False,
                output="",
                error=body.get("error", "Unknown error"),
            )

        data = body.get("data", {})
        result_count = len(data.get("result", []))
        output = _format_prometheus_result(data)
        logger.info(f"[prometheus] Result: {result_count} series")
        return ServiceResult(success=True, output=output)

    async def close(self) -> None:
        pass  # httpx client is created per-request
