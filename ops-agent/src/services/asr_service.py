import base64

import orjson
import websockets

from src.config import Settings
from src.lib.logger import logger


class ASRProxySession:
    """Proxy session between client and DashScope Realtime ASR WebSocket."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._ws: websockets.ClientConnection | None = None

    async def connect(self) -> None:
        url = f"{self._settings.dashscope_ws_url}?model={self._settings.asr_model}"
        self._ws = await websockets.connect(
            url,
            additional_headers={
                "Authorization": f"Bearer {self._settings.dashscope_api_key}",
                "OpenAI-Beta": "realtime=v1",
            },
        )

    async def send_audio(self, data: bytes) -> None:
        if self._ws is not None:
            payload = {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(data).decode("ascii"),
            }
            await self._ws.send(orjson.dumps(payload))

    async def finish_session(self) -> None:
        if self._ws is None:
            return
        await self._ws.send(orjson.dumps({"type": "session.finish"}))

    async def receive_results(self):
        """Async generator yielding parsed result dicts from DashScope Realtime API."""
        assert self._ws is not None
        async for raw in self._ws:
            if isinstance(raw, bytes):
                continue
            try:
                msg = orjson.loads(raw)
            except Exception:
                logger.warning("ASR: failed to parse upstream message")
                continue

            msg_type = msg.get("type", "")

            if msg_type == "error":
                error_msg = msg.get("error", {}).get("message", "unknown error")
                logger.error(f"ASR upstream error: {error_msg}")
                yield {"type": "error", "message": error_msg}
                return
            elif msg_type == "session.created":
                yield {"type": "started"}
            elif msg_type == "conversation.item.input_audio_transcription.text":
                yield {"type": "result", "text": msg.get("text", ""), "is_end": False}
            elif msg_type == "conversation.item.input_audio_transcription.completed":
                yield {"type": "result", "text": msg.get("transcript", ""), "is_end": True}
            elif msg_type == "session.finished":
                yield {"type": "finished"}
                return

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
