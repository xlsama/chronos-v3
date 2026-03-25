import asyncio
import base64
import io
import json

import av
import orjson
import websockets

from src.env import get_settings
from src.lib.logger import get_logger

log = get_logger()

CHUNK_SAMPLES = 3200  # 200ms @ 16kHz
BYTES_PER_SAMPLE = 2  # Int16
CHUNK_BYTES = CHUNK_SAMPLES * BYTES_PER_SAMPLE


def _convert_to_pcm(audio_data: bytes) -> bytes:
    """Convert audio (webm/opus/mp4/etc.) to raw PCM Int16 mono 16kHz using PyAV."""
    container = av.open(io.BytesIO(audio_data))
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

    pcm_parts: list[bytes] = []
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            pcm_parts.append(resampled.to_ndarray().tobytes())

    container.close()
    return b"".join(pcm_parts)


async def transcribe_audio(audio_data: bytes, filename: str) -> str:
    """Convert audio to PCM, stream to DashScope Realtime API, return text."""
    settings = get_settings()

    # Convert to PCM in a thread (CPU-bound)
    pcm_data = await asyncio.to_thread(_convert_to_pcm, audio_data)
    if not pcm_data:
        return ""

    # Connect to DashScope Realtime API
    url = f"{settings.dashscope_ws_url}?model={settings.stt_model}"
    ws = await websockets.connect(
        url,
        additional_headers={
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "OpenAI-Beta": "realtime=v1",
        },
    )

    texts: list[str] = []
    try:
        # Stream PCM chunks
        for offset in range(0, len(pcm_data), CHUNK_BYTES):
            chunk = pcm_data[offset : offset + CHUNK_BYTES]
            msg = json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("ascii"),
            })
            await ws.send(msg)

        # Signal end of audio
        await ws.send(json.dumps({"type": "session.finish"}))

        # Collect results
        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            try:
                msg = orjson.loads(raw)
            except Exception:
                continue

            msg_type = msg.get("type", "")
            if msg_type == "conversation.item.input_audio_transcription.completed":
                text = msg.get("transcript", "")
                if text:
                    texts.append(text)
            elif msg_type == "session.finished":
                break
            elif msg_type == "error":
                error_msg = msg.get("error", {}).get("message", "unknown error")
                log.error("STT upstream error", message=error_msg)
                raise RuntimeError(f"STT error: {error_msg}")
    finally:
        await ws.close()

    return "".join(texts)
