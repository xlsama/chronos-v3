import re
import time
import uuid

from sqlalchemy import func, select

from src.db.connection import get_session_factory
from src.db.models import Incident, Message
from src.lib.logger import get_logger
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
    log = get_logger(component="post_incident", sid=sid)
    log.info(
        "auto_save_history called",
        incident_id=incident_id,
        summary_md_len=len(summary_md) if summary_md else 0,
    )
    if not summary_md:
        log.info("summary_md is empty, skipping auto-save")
        return

    has_root = _has_root_cause(summary_md)
    log.info("Root cause check", has_root_cause=has_root)
    if not has_root:
        return

    async with get_session_factory()() as session:
        # Check tool_use events with ssh_bash/bash/service_exec → agent executed commands
        tool_count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.incident_id == uuid.UUID(incident_id),
                Message.event_type == "tool_use",
                Message.content.in_(["ssh_bash", "bash", "service_exec"]),
            )
        )
        log.info("Exec tool calls check", exec_tool_calls=tool_count)
        if not tool_count:
            return

        incident = await session.get(Incident, uuid.UUID(incident_id))
        if not incident:
            return
        log.info("Memory check", saved_to_memory=incident.saved_to_memory)
        if incident.saved_to_memory:
            return

        service = IncidentHistoryService(session=session)
        log.info("Calling service.auto_save()")
        t0 = time.monotonic()
        result = await service.auto_save(incident, summary_md)
        save_elapsed = time.monotonic() - t0
        log.info("service.auto_save() completed", elapsed=f"{save_elapsed:.2f}s")
        if result is None:
            log.warning("Auto-save returned None (unexpected)")
            return
        log.info("Auto-save result", result=result)
