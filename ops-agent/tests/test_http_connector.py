"""Tests for HTTPConnector — mock httpx.AsyncClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.http import HTTPConnector, HTTPResult


@pytest.fixture
def connector():
    return HTTPConnector(timeout=30)


def _mock_response(status_code=200, text="ok", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {"content-type": "application/json"}
    return resp


@patch("src.connectors.http.httpx.AsyncClient")
async def test_get_request(mock_client_cls, connector: HTTPConnector):
    mock_client = AsyncMock()
    mock_client.request.return_value = _mock_response(text='{"data": 1}')
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await connector.request("GET", "https://api.example.com/data")

    assert isinstance(result, HTTPResult)
    assert result.status_code == 200
    assert result.body == '{"data": 1}'
    mock_client.request.assert_called_once_with(
        method="GET",
        url="https://api.example.com/data",
        headers=None,
        content=None,
    )


@patch("src.connectors.http.httpx.AsyncClient")
async def test_post_request(mock_client_cls, connector: HTTPConnector):
    mock_client = AsyncMock()
    mock_client.request.return_value = _mock_response(status_code=201, text='{"id": 1}')
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await connector.request("POST", "https://api.example.com/items", body='{"name": "test"}')

    assert result.status_code == 201
    mock_client.request.assert_called_once_with(
        method="POST",
        url="https://api.example.com/items",
        headers=None,
        content='{"name": "test"}',
    )


@patch("src.connectors.http.httpx.AsyncClient")
async def test_put_request(mock_client_cls, connector: HTTPConnector):
    mock_client = AsyncMock()
    mock_client.request.return_value = _mock_response(text="updated")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await connector.request("put", "https://api.example.com/items/1", body='{"name": "updated"}')

    assert result.status_code == 200
    mock_client.request.assert_called_once_with(
        method="PUT",
        url="https://api.example.com/items/1",
        headers=None,
        content='{"name": "updated"}',
    )


@patch("src.connectors.http.httpx.AsyncClient")
async def test_delete_request(mock_client_cls, connector: HTTPConnector):
    mock_client = AsyncMock()
    mock_client.request.return_value = _mock_response(status_code=204, text="")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await connector.request("DELETE", "https://api.example.com/items/1")

    assert result.status_code == 204


@patch("src.connectors.http.httpx.AsyncClient")
async def test_response_truncation(mock_client_cls, connector: HTTPConnector):
    long_body = "x" * 20000
    mock_client = AsyncMock()
    mock_client.request.return_value = _mock_response(text=long_body)
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await connector.request("GET", "https://api.example.com/big")

    assert len(result.body) == 10000


@patch("src.connectors.http.httpx.AsyncClient")
async def test_custom_headers(mock_client_cls, connector: HTTPConnector):
    mock_client = AsyncMock()
    mock_client.request.return_value = _mock_response(text="ok")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    headers = {"Authorization": "Bearer token123"}
    result = await connector.request("GET", "https://api.example.com/secure", headers=headers)

    assert result.status_code == 200
    mock_client.request.assert_called_once_with(
        method="GET",
        url="https://api.example.com/secure",
        headers=headers,
        content=None,
    )


@patch("src.connectors.http.httpx.AsyncClient")
async def test_request_body_passed(mock_client_cls, connector: HTTPConnector):
    mock_client = AsyncMock()
    mock_client.request.return_value = _mock_response(text="ok")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    await connector.request("POST", "https://api.example.com/data", body="payload")

    call_kwargs = mock_client.request.call_args
    assert call_kwargs.kwargs["content"] == "payload"
