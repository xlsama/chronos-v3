import re
import uuid

from sqlalchemy import func, select

from src.db.connection import get_session_factory
from src.db.models import Incident, Message
from src.lib.logger import logger
from src.services.incident_history_service import IncidentHistoryService


def _has_root_cause(summary_md: str) -> bool:
    """Check if summary has a meaningful root cause analysis section."""
    match = re.search(r"##\s*根因分析\s*\n(.*?)(?=\n##|\Z)", summary_md, re.DOTALL)
    if not match:
        return False
    content = match.group(1).strip()
    if len(content) < 20:
        return False
    skip_patterns = ["暂无", "无法确定", "未能确定", "尚不明确"]
    return not any(p in content for p in skip_patterns)


async def auto_save_history(incident_id: str, summary_md: str) -> None:
    """Auto-save incident history with similarity dedup."""
    sid = incident_id[:8]
    if not summary_md:
        logger.info(f"[{sid}] [history] Check: summary_md is empty, skipping auto-save")
        return

    has_root = _has_root_cause(summary_md)
    logger.info(f"[{sid}] [history] Check: has_root_cause={has_root}")
    if not has_root:
        return

    async with get_session_factory()() as session:
        # Check tool_call events with bash → agent executed commands
        tool_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.incident_id == uuid.UUID(incident_id),
                Message.event_type == "tool_call",
                Message.content == "bash",
            )
        )
        logger.info(f"[{sid}] [history] Check: bash_tool_calls={tool_count}")
        if not tool_count:
            return

        incident = await session.get(Incident, uuid.UUID(incident_id))
        if not incident:
            return
        logger.info(f"[{sid}] [history] Check: saved_to_memory={incident.saved_to_memory}")
        if incident.saved_to_memory:
            return

        service = IncidentHistoryService(session=session)
        result = await service.auto_save(incident, summary_md)
        logger.info(f"[{sid}] [history] Auto-save result: {result.get('action')}")
