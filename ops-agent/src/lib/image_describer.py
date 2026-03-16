"""Image describer using VL (Vision-Language) model."""

import base64
from pathlib import Path

from openai import AsyncOpenAI

from src.config import get_settings

MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _get_mime_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return MIME_MAP.get(ext, "image/png")


class ImageDescriber:
    def __init__(self):
        s = get_settings()
        self.client = AsyncOpenAI(api_key=s.dashscope_api_key, base_url=s.llm_base_url)
        self.model = s.vision_model

    async def describe(self, image_bytes: bytes, filename: str) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        mime = _get_mime_type(filename)
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": "请详细描述这张图片的内容。"},
                ],
            }],
            max_tokens=1000,
        )
        return resp.choices[0].message.content
