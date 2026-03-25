import httpx

from src.env import get_settings
from src.lib.logger import get_logger

log = get_logger()


async def transcribe_audio(audio_data: bytes, filename: str) -> str:
    """Send audio file to DashScope transcription API and return text."""
    settings = get_settings()
    url = f"{settings.llm_base_url}/audio/transcriptions"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
            files={"file": (filename, audio_data)},
            data={"model": settings.asr_model},
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("text", "")
