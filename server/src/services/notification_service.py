import asyncio
import uuid

from sqlalchemy import select

from src.env import get_settings
from src.db.connection import get_session_factory
from src.db.models import NotificationSetting, Project
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

SEVERITY_LABEL = {
    "P0": "🔴 P0 - Critical",
    "P1": "🟠 P1 - High",
    "P2": "🟡 P2 - Medium",
    "P3": "🟢 P3 - Low",
}

RISK_LABEL = {
    "HIGH": "🔴 HIGH",
    "MEDIUM": "🟡 MEDIUM",
    "LOW": "🟢 LOW",
}

MAX_FIELD_LEN = 200


def _truncate(text: str, max_len: int = MAX_FIELD_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


async def _resolve_project_name(session, project_id: str) -> str | None:
    try:
        project = await session.get(Project, uuid.UUID(project_id))
        return project.name if project else None
    except (ValueError, Exception):
        return None


async def _send_notification(
    event_type: str,
    incident_id: str,
    title: str,
    *,
    severity: str = "",
    project_id: str = "",
    command: str = "",
    risk_level: str = "",
    explanation: str = "",
    question: str = "",
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

            # Resolve project name within the same session
            project_name = None
            if project_id:
                project_name = await _resolve_project_name(session, project_id)

        crypto = CryptoService(get_settings().encryption_key)
        webhook_url = crypto.decrypt(setting.encrypted_webhook_url)
        sign_key = crypto.decrypt(setting.encrypted_sign_key) if setting.encrypted_sign_key else None

        label, color = EVENT_TYPE_MAP.get(event_type, (event_type, "blue"))

        # Build fields
        fields: list[tuple[str, str]] = [
            ("事件", _truncate(title or incident_id)),
        ]
        if project_name:
            fields.append(("项目", project_name))
        if severity:
            fields.append(("级别", SEVERITY_LABEL.get(severity, severity)))
        fields.append(("状态", label))

        # Type-specific fields
        if event_type == "need_approval":
            if command:
                fields.append(("命令", f"`{_truncate(command)}`"))
            if risk_level:
                fields.append(("风险等级", RISK_LABEL.get(risk_level, risk_level)))
            if explanation:
                fields.append(("说明", _truncate(explanation)))
        elif event_type == "ask_human":
            if question:
                fields.append(("问题", _truncate(question)))

        fields.append(("ID", incident_id[:8]))

        card_title = f"[Chronos] {label}"
        await send_feishu_card(webhook_url, card_title, fields, color, sign_key)
    except Exception:
        logger.exception(f"Failed to send notification for incident {incident_id}")


def notify_fire_and_forget(
    event_type: str,
    incident_id: str,
    title: str,
    *,
    severity: str = "",
    project_id: str = "",
    command: str = "",
    risk_level: str = "",
    explanation: str = "",
    question: str = "",
) -> None:
    asyncio.create_task(
        _send_notification(
            event_type,
            incident_id,
            title,
            severity=severity,
            project_id=project_id,
            command=command,
            risk_level=risk_level,
            explanation=explanation,
            question=question,
        )
    )
