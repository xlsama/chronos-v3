"""Tests for ASR WebSocket endpoint."""

import asyncio
from unittest.mock import AsyncMock, patch

import orjson
import pytest
from starlette.testclient import TestClient

from src.main import app


@pytest.fixture
def mock_asr_session():
    """Mock ASRProxySession to avoid connecting to real DashScope."""
    with patch("src.api.asr.ASRProxySession") as MockClass:
        session = AsyncMock()
        MockClass.return_value = session

        session.connect = AsyncMock()
        session.send_audio = AsyncMock()
        session.finish_session = AsyncMock()
        session.close = AsyncMock()

        yield session, MockClass


class TestASRStream:
    def test_connect_and_receive_result(self, mock_asr_session):
        """Test basic flow: connect → receive results → finished."""
        session, _ = mock_asr_session

        results = [
            {"type": "started"},
            {"type": "result", "text": "你好", "is_end": False},
            {"type": "result", "text": "你好世界", "is_end": True},
            {"type": "finished"},
        ]

        async def fake_receive_results():
            for r in results:
                yield r

        session.receive_results = fake_receive_results

        client = TestClient(app)
        with client.websocket_connect("/api/asr/stream") as ws:
            for expected in results:
                data = ws.receive_json()
                assert data["type"] == expected["type"]
                if "text" in expected:
                    assert data["text"] == expected["text"]

    def test_connect_failure_returns_error(self, mock_asr_session):
        """If DashScope connection fails, client should get error message."""
        session, _ = mock_asr_session
        session.connect = AsyncMock(side_effect=Exception("connection refused"))

        client = TestClient(app)
        with client.websocket_connect("/api/asr/stream") as ws:
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "连接失败" in data["message"]

    def test_send_audio_forwarded(self, mock_asr_session):
        """Binary audio data should be forwarded to DashScope session."""
        session, _ = mock_asr_session

        async def fake_receive_results():
            await asyncio.sleep(0.5)
            yield {"type": "finished"}

        session.receive_results = fake_receive_results

        client = TestClient(app)
        with client.websocket_connect("/api/asr/stream") as ws:
            ws.send_bytes(b"\x00\x01\x02\x03")
            ws.send_text(orjson.dumps({"action": "stop"}).decode())
            data = ws.receive_json()
            assert data["type"] == "finished"

        session.send_audio.assert_called_with(b"\x00\x01\x02\x03")
        session.finish_session.assert_called_once()

    def test_stop_action_triggers_finish(self, mock_asr_session):
        """Sending stop action should call finish_session on session."""
        session, _ = mock_asr_session

        async def fake_receive_results():
            await asyncio.sleep(0.1)
            yield {"type": "result", "text": "测试", "is_end": True}
            yield {"type": "finished"}

        session.receive_results = fake_receive_results

        client = TestClient(app)
        with client.websocket_connect("/api/asr/stream") as ws:
            ws.send_text(orjson.dumps({"action": "stop"}).decode())
            messages = []
            while True:
                try:
                    data = ws.receive_json()
                    messages.append(data)
                    if data["type"] == "finished":
                        break
                except Exception:
                    break

        session.finish_session.assert_called_once()
