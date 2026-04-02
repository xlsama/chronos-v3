"""Cron 任务共享的数据获取工具。"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.db.connection import get_session_factory
from src.db.models import IncidentHistory, Project, ProjectDocument
from src.lib.logger import get_logger

log = get_logger(component="cron")


async def fetch_recent_data() -> tuple[list[IncidentHistory], list[dict]]:
    """获取最近 24 小时的历史事件 + 所有项目的 MEMORY.md。

    Returns:
        (incidents, memory_docs)
        memory_docs 每项包含: project_id, project_name, project_slug, content
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    async with get_session_factory()() as session:
        result = await session.execute(
            select(IncidentHistory)
            .where(IncidentHistory.last_seen_at >= since)
            .order_by(IncidentHistory.last_seen_at.desc())
        )
        incidents = list(result.scalars().all())

        result = await session.execute(
            select(ProjectDocument, Project.id, Project.name, Project.slug)
            .join(Project, ProjectDocument.project_id == Project.id)
            .where(ProjectDocument.doc_type == "memory_config")
        )
        memory_docs = [
            {
                "project_id": row[1],
                "project_name": row[2],
                "project_slug": row[3],
                "content": row[0].content,
            }
            for row in result.all()
        ]

    log.info(
        "Fetched recent data",
        incidents=len(incidents),
        memory_docs=len(memory_docs),
    )
    return incidents, memory_docs
