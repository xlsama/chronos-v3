"""Tests for query_metrics and query_logs tools."""

from unittest.mock import AsyncMock, patch

import pytest

from src.tools.monitoring_tools import query_metrics, query_logs


@patch("src.tools.monitoring_tools._get_monitoring_source")
async def test_query_metrics_instant(mock_get_source):
    mock_get_source.return_value = ("http://prometheus:9090", {"Authorization": "Bearer tok"})

    mock_connector = AsyncMock()
    mock_connector.query_instant.return_value = {
        "status": "success",
        "data": {"resultType": "vector", "result": [{"value": [1, "0.5"]}]},
    }

    with patch("src.connectors.prometheus.PrometheusConnector", return_value=mock_connector):
        result = await query_metrics(project_id="proj-1", query="up")

    assert result["error"] is None
    assert result["status"] == "success"
    mock_connector.query_instant.assert_called_once_with(query="up")


@patch("src.tools.monitoring_tools._get_monitoring_source")
async def test_query_metrics_range(mock_get_source):
    mock_get_source.return_value = ("http://prometheus:9090", None)

    mock_connector = AsyncMock()
    mock_connector.query_range.return_value = {
        "status": "success",
        "data": {"resultType": "matrix", "result": []},
    }

    with patch("src.connectors.prometheus.PrometheusConnector", return_value=mock_connector):
        result = await query_metrics(
            project_id="proj-1",
            query="rate(http_requests_total[5m])",
            start="t1",
            end="t2",
            step="120s",
        )

    assert result["error"] is None
    mock_connector.query_range.assert_called_once_with(
        query="rate(http_requests_total[5m])", start="t1", end="t2", step="120s"
    )


@patch("src.tools.monitoring_tools._get_monitoring_source")
async def test_query_metrics_no_source(mock_get_source):
    mock_get_source.return_value = (None, None)

    result = await query_metrics(project_id="proj-1", query="up")

    assert "error" in result
    assert "No Prometheus source" in result["error"]


@patch("src.tools.monitoring_tools._get_monitoring_source")
async def test_query_logs_success(mock_get_source):
    mock_get_source.return_value = ("http://loki:3100", None)

    mock_connector = AsyncMock()
    mock_connector.query_range.return_value = {
        "status": "success",
        "data": {
            "result": [
                {
                    "stream": {"app": "nginx", "env": "prod"},
                    "values": [
                        ["1710000000000000000", "GET /api/health 200"],
                        ["1710000001000000000", "POST /api/data 201"],
                    ],
                }
            ]
        },
    }

    with patch("src.connectors.loki.LokiConnector", return_value=mock_connector):
        result = await query_logs(project_id="proj-1", query='{app="nginx"}')

    assert result["error"] is None
    assert result["count"] == 2
    assert "app=nginx" in result["logs"]
    assert "GET /api/health 200" in result["logs"]


@patch("src.tools.monitoring_tools._get_monitoring_source")
async def test_query_logs_no_source(mock_get_source):
    mock_get_source.return_value = (None, None)

    result = await query_logs(project_id="proj-1", query='{app="test"}')

    assert "error" in result
    assert "No Loki source" in result["error"]


@patch("src.tools.monitoring_tools._get_monitoring_source")
async def test_query_metrics_exception(mock_get_source):
    mock_get_source.return_value = ("http://prometheus:9090", None)

    mock_connector = AsyncMock()
    mock_connector.query_instant.side_effect = Exception("timeout")

    with patch("src.connectors.prometheus.PrometheusConnector", return_value=mock_connector):
        result = await query_metrics(project_id="proj-1", query="up")

    assert result["error"] == "timeout"


@patch("src.tools.monitoring_tools._get_monitoring_source")
async def test_query_logs_exception(mock_get_source):
    mock_get_source.return_value = ("http://loki:3100", None)

    mock_connector = AsyncMock()
    mock_connector.query_range.side_effect = Exception("connection error")

    with patch("src.connectors.loki.LokiConnector", return_value=mock_connector):
        result = await query_logs(project_id="proj-1", query='{app="test"}')

    assert result["error"] == "connection error"
