import asyncio

from sqlalchemy import select

from src.config import get_settings
from src.db.connection import get_session_factory
from src.db.models import NotificationSetting
from src.lib.feishu import send_feishu_card
from src.lib.logger import logger
from src.services.crypto import CryptoService

EVENT_TYPE_MAP = {
    "open": ("新事件", "red"),
    "investigating": ("开始排查", "blue"),
    "resolved": ("已解决", "green"),
    "stopped": ("已停止", "orange"),
    "ask_human": ("需要人工输入", "orange"),
    "need_approval": ("需要审批", "orange"),
}


async def _send_notification(
    event_type: str,
    incident_id: str,
    title: str,
    detail: str = "",
) -> None:
    try:
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(NotificationSetting).where(
                    NotificationSetting.platform == "feishu",
                    NotificationSetting.enabled.is_(True),
                )
            )
            setting = result.scalar_one_or_none()
            if not setting:
                return

        crypto = CryptoService(get_settings().encryption_key)
        webhook_url = crypto.decrypt(setting.encrypted_webhook_url)
        sign_key = crypto.decrypt(setting.encrypted_sign_key) if setting.encrypted_sign_key else None

        label, color = EVENT_TYPE_MAP.get(event_type, (event_type, "blue"))

        fields: list[tuple[str, str]] = [
            ("事件", title or incident_id),
            ("状态", label),
        ]
        if detail:
            fields.append(("详情", detail))

        card_title = f"[Chronos] {label}"
        await send_feishu_card(webhook_url, card_title, fields, color, sign_key)
    except Exception:
        logger.exception(f"Failed to send notification for incident {incident_id}")


def notify_fire_and_forget(
    event_type: str,
    incident_id: str,
    title: str,
    detail: str = "",
) -> None:
    asyncio.create_task(_send_notification(event_type, incident_id, title, detail))
