import base64
import hashlib
import hmac
import time

import httpx

from src.lib.logger import get_logger


def _compute_feishu_sign(timestamp: str, sign_key: str) -> str:
    string_to_sign = f"{timestamp}\n{sign_key}"
    hmac_code = hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode()


async def send_feishu_message(webhook_url: str, text: str, sign_key: str | None = None) -> None:
    body: dict = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if sign_key:
        timestamp = str(int(time.time()))
        body["timestamp"] = timestamp
        body["sign"] = _compute_feishu_sign(timestamp, sign_key)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=body)
        result = resp.json()
        if result.get("code") != 0:
            raise Exception(f"Feishu API error: {result.get('msg', 'unknown')}")


async def send_feishu_card(
    webhook_url: str,
    title: str,
    fields: list[tuple[str, str]],
    color: str = "blue",
    sign_key: str | None = None,
) -> None:
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"}}
        for label, value in fields
    ]

    card = {
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": color,
        },
        "elements": elements,
    }

    body: dict = {
        "msg_type": "interactive",
        "card": card,
    }
    if sign_key:
        timestamp = str(int(time.time()))
        body["timestamp"] = timestamp
        body["sign"] = _compute_feishu_sign(timestamp, sign_key)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=body)
        result = resp.json()
        if result.get("code") != 0:
            raise Exception(f"Feishu API error: {result.get('msg', 'unknown')}")
