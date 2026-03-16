import uuid

import orjson

from src.lib.logger import logger


async def _get_monitoring_source(project_id: str, source_type: str):
    """Look up a monitoring source from DB."""
    from src.config import get_settings
    from src.db.connection import get_session_factory
    from src.db.models import MonitoringSource
    from src.services.crypto import CryptoService

    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(MonitoringSource).where(
                MonitoringSource.project_id == uuid.UUID(project_id),
                MonitoringSource.source_type == source_type,
            )
        )
        source = result.scalar_one_or_none()
        if not source:
            return None, None

        headers = None
        if source.conn_config:
            crypto = CryptoService(key=get_settings().encryption_key)
            config = orjson.loads(crypto.decrypt(source.conn_config))
            if "auth_header" in config:
                headers = {"Authorization": config["auth_header"]}

        return source.endpoint, headers


async def query_metrics(
    project_id: str,
    query: str,
    start: str | None = None,
    end: str | None = None,
    step: str = "60s",
) -> dict:
    """Query Prometheus metrics."""
    from src.connectors.prometheus import PrometheusConnector

    endpoint, headers = await _get_monitoring_source(project_id, "prometheus")
    if not endpoint:
        return {"error": f"No Prometheus source configured for project {project_id}"}

    connector = PrometheusConnector(endpoint=endpoint, headers=headers)

    try:
        if start and end:
            result = await connector.query_range(query=query, start=start, end=end, step=step)
        else:
            result = await connector.query_instant(query=query)

        # Truncate large results
        result_str = orjson.dumps(result).decode()
        if len(result_str) > 10000:
            result_str = result_str[:10000] + "... (truncated)"
            return {"data": result_str, "error": None}

        return {"data": result.get("data", {}), "status": result.get("status"), "error": None}
    except Exception as e:
        logger.error(f"Prometheus query failed: {e}")
        return {"error": str(e)}


async def query_logs(
    project_id: str,
    query: str,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
) -> dict:
    """Query Loki logs."""
    from src.connectors.loki import LokiConnector

    endpoint, headers = await _get_monitoring_source(project_id, "loki")
    if not endpoint:
        return {"error": f"No Loki source configured for project {project_id}"}

    connector = LokiConnector(endpoint=endpoint, headers=headers)

    try:
        result = await connector.query_range(query=query, start=start, end=end, limit=limit)

        # Format log lines for readability
        data = result.get("data", {})
        streams = data.get("result", [])
        lines = []
        for stream in streams:
            labels = stream.get("stream", {})
            label_str = ", ".join(f"{k}={v}" for k, v in labels.items())
            for ts, line in stream.get("values", []):
                lines.append(f"[{label_str}] {line}")

        output = "\n".join(lines[:limit])
        if len(output) > 10000:
            output = output[:10000] + "\n... (truncated)"

        return {"logs": output, "count": len(lines), "error": None}
    except Exception as e:
        logger.error(f"Loki query failed: {e}")
        return {"error": str(e)}
