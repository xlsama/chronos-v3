"""Tests for LokiConnector — mock httpx.AsyncClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.loki import LokiConnector


@pytest.fixture
def connector():
    return LokiConnector(endpoint="http://loki:3100", headers={"X-Org": "test"})


def _mock_json_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@patch("src.connectors.loki.httpx.AsyncClient")
async def test_query_range(mock_client_cls, connector: LokiConnector):
    mock_client = AsyncMock()
    expected = {
        "status": "success",
        "data": {"result": [{"stream": {"app": "nginx"}, "values": [["ts1", "log line"]]}]},
    }
    mock_client.get.return_value = _mock_json_response(expected)
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await connector.query_range(
        query='{app="nginx"}',
        start="2026-03-16T00:00:00Z",
        end="2026-03-16T01:00:00Z",
        limit=50,
    )

    assert result == expected
    mock_client.get.assert_called_once_with(
        "http://loki:3100/loki/api/v1/query_range",
        params={
            "query": '{app="nginx"}',
            "limit": "50",
            "start": "2026-03-16T00:00:00Z",
            "end": "2026-03-16T01:00:00Z",
        },
        headers={"X-Org": "test"},
    )


@patch("src.connectors.loki.httpx.AsyncClient")
async def test_query_range_without_time_params(mock_client_cls, connector: LokiConnector):
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_json_response({"status": "success", "data": {}})
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    await connector.query_range(query='{app="test"}')

    params = mock_client.get.call_args.kwargs["params"]
    assert "start" not in params
    assert "end" not in params
    assert params["limit"] == "100"


@patch("src.connectors.loki.httpx.AsyncClient")
async def test_test_connection_success(mock_client_cls, connector: LokiConnector):
    mock_client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 200
    mock_client.get.return_value = resp
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    ok = await connector.test_connection()

    assert ok is True
    call_args = mock_client.get.call_args
    assert "/ready" in call_args[0][0]


@patch("src.connectors.loki.httpx.AsyncClient")
async def test_test_connection_failure(mock_client_cls, connector: LokiConnector):
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection refused")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    ok = await connector.test_connection()

    assert ok is False


@patch("src.connectors.loki.httpx.AsyncClient")
async def test_test_connection_non_200(mock_client_cls, connector: LokiConnector):
    mock_client = AsyncMock()
    resp = MagicMock()
    resp.status_code = 503
    mock_client.get.return_value = resp
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    ok = await connector.test_connection()

    assert ok is False
