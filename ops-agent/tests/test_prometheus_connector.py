"""Tests for PrometheusConnector — mock httpx.AsyncClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.prometheus import PrometheusConnector


@pytest.fixture
def connector():
    return PrometheusConnector(endpoint="http://prometheus:9090", headers={"X-Custom": "val"})


def _mock_json_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@patch("src.connectors.prometheus.httpx.AsyncClient")
async def test_query_instant(mock_client_cls, connector: PrometheusConnector):
    mock_client = AsyncMock()
    expected = {"status": "success", "data": {"resultType": "vector", "result": []}}
    mock_client.get.return_value = _mock_json_response(expected)
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await connector.query_instant("up")

    assert result == expected
    mock_client.get.assert_called_once_with(
        "http://prometheus:9090/api/v1/query",
        params={"query": "up"},
        headers={"X-Custom": "val"},
    )


@patch("src.connectors.prometheus.httpx.AsyncClient")
async def test_query_range(mock_client_cls, connector: PrometheusConnector):
    mock_client = AsyncMock()
    expected = {"status": "success", "data": {"resultType": "matrix", "result": []}}
    mock_client.get.return_value = _mock_json_response(expected)
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await connector.query_range(
        query="rate(http_requests_total[5m])",
        start="2026-03-16T00:00:00Z",
        end="2026-03-16T01:00:00Z",
        step="120s",
    )

    assert result == expected
    mock_client.get.assert_called_once_with(
        "http://prometheus:9090/api/v1/query_range",
        params={
            "query": "rate(http_requests_total[5m])",
            "start": "2026-03-16T00:00:00Z",
            "end": "2026-03-16T01:00:00Z",
            "step": "120s",
        },
        headers={"X-Custom": "val"},
    )


@patch("src.connectors.prometheus.httpx.AsyncClient")
async def test_test_connection_success(mock_client_cls, connector: PrometheusConnector):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_json_response({"status": "success"})
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    ok = await connector.test_connection()

    assert ok is True
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert "/api/v1/status/buildinfo" in call_args[0][0]


@patch("src.connectors.prometheus.httpx.AsyncClient")
async def test_test_connection_failure(mock_client_cls, connector: PrometheusConnector):
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection refused")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    ok = await connector.test_connection()

    assert ok is False


@patch("src.connectors.prometheus.httpx.AsyncClient")
async def test_query_range_default_step(mock_client_cls, connector: PrometheusConnector):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_json_response({"status": "success", "data": {}})
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    await connector.query_range(query="up", start="t1", end="t2")

    params = mock_client.get.call_args.kwargs["params"]
    assert params["step"] == "60s"
