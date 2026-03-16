"""Tests for http_request tool."""

from unittest.mock import AsyncMock, patch

import pytest

from src.connectors.http import HTTPResult
from src.tools.http_tools import http_request


@patch("src.tools.http_tools.HTTPConnector")
async def test_http_request_success(mock_connector_cls):
    mock_connector = AsyncMock()
    mock_connector.request.return_value = HTTPResult(
        status_code=200,
        body='{"result": "ok"}',
        headers={"content-type": "application/json"},
    )
    mock_connector_cls.return_value = mock_connector

    result = await http_request(method="GET", url="https://api.example.com/health")

    assert result["status_code"] == 200
    assert result["body"] == '{"result": "ok"}'
    assert result["error"] is None


@patch("src.tools.http_tools.HTTPConnector")
async def test_http_request_with_headers(mock_connector_cls):
    mock_connector = AsyncMock()
    mock_connector.request.return_value = HTTPResult(
        status_code=200, body="ok", headers={}
    )
    mock_connector_cls.return_value = mock_connector

    result = await http_request(
        method="GET",
        url="https://api.example.com/data",
        headers='{"Authorization": "Bearer token"}',
    )

    assert result["error"] is None
    mock_connector.request.assert_called_once_with(
        method="GET",
        url="https://api.example.com/data",
        headers={"Authorization": "Bearer token"},
        body=None,
    )


async def test_http_request_invalid_headers_json():
    result = await http_request(
        method="GET",
        url="https://api.example.com/data",
        headers="not-valid-json",
    )

    assert "error" in result
    assert "Invalid headers JSON" in result["error"]


@patch("src.tools.http_tools.HTTPConnector")
async def test_http_request_connection_error(mock_connector_cls):
    mock_connector = AsyncMock()
    mock_connector.request.side_effect = Exception("Connection refused")
    mock_connector_cls.return_value = mock_connector

    result = await http_request(method="GET", url="https://unreachable.example.com")

    assert result["error"] == "Connection refused"
    assert "status_code" not in result


@patch("src.tools.http_tools.HTTPConnector")
async def test_http_request_with_body(mock_connector_cls):
    mock_connector = AsyncMock()
    mock_connector.request.return_value = HTTPResult(
        status_code=201, body='{"id": 1}', headers={}
    )
    mock_connector_cls.return_value = mock_connector

    result = await http_request(
        method="POST",
        url="https://api.example.com/items",
        body='{"name": "test"}',
    )

    assert result["status_code"] == 201
    mock_connector.request.assert_called_once_with(
        method="POST",
        url="https://api.example.com/items",
        headers=None,
        body='{"name": "test"}',
    )
