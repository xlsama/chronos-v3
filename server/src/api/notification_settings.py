from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    NotificationSettingsResponse,
    NotificationSettingsUpsert,
    WebhookTestRequest,
    WebhookTestResponse,
)
from src.env import get_settings
from src.db.connection import get_session
from src.db.models import NotificationSetting
from src.lib.feishu import send_feishu_message
from src.lib.logger import get_logger
from src.services.crypto import CryptoService

log = get_logger()

router = APIRouter(prefix="/api/notification-settings", tags=["notification-settings"])


def _get_crypto() -> CryptoService:
    return CryptoService(get_settings().encryption_key)


@router.post("/test/webhook", response_model=WebhookTestResponse)
async def test_webhook(body: WebhookTestRequest):
    try:
        await send_feishu_message(body.webhook_url, "Chronos 测试消息 - 通知配置成功！", body.sign_key)
        return WebhookTestResponse(success=True, message="测试消息发送成功")
    except Exception as e:
        log.warning("Webhook test failed", error=str(e))
        return WebhookTestResponse(success=False, message=str(e))


@router.get("/{platform}", response_model=NotificationSettingsResponse | None)
async def get_notification_settings(
    platform: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(NotificationSetting).where(NotificationSetting.platform == platform)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        return None

    crypto = _get_crypto()
    return NotificationSettingsResponse(
        id=setting.id,
        platform=setting.platform,
        webhook_url=crypto.decrypt(setting.encrypted_webhook_url),
        sign_key=crypto.decrypt(setting.encrypted_sign_key) if setting.encrypted_sign_key else None,
        enabled=setting.enabled,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


@router.put("/{platform}", response_model=NotificationSettingsResponse)
async def upsert_notification_settings(
    platform: str,
    body: NotificationSettingsUpsert,
    session: AsyncSession = Depends(get_session),
):
    crypto = _get_crypto()

    result = await session.execute(
        select(NotificationSetting).where(NotificationSetting.platform == platform)
    )
    setting = result.scalar_one_or_none()

    encrypted_url = crypto.encrypt(body.webhook_url)
    encrypted_key = crypto.encrypt(body.sign_key) if body.sign_key else None

    if setting:
        setting.encrypted_webhook_url = encrypted_url
        setting.encrypted_sign_key = encrypted_key
        setting.enabled = body.enabled
    else:
        setting = NotificationSetting(
            platform=platform,
            encrypted_webhook_url=encrypted_url,
            encrypted_sign_key=encrypted_key,
            enabled=body.enabled,
        )
        session.add(setting)

    await session.commit()
    await session.refresh(setting)

    return NotificationSettingsResponse(
        id=setting.id,
        platform=setting.platform,
        webhook_url=body.webhook_url,
        sign_key=body.sign_key,
        enabled=setting.enabled,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )
