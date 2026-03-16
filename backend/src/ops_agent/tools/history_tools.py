import uuid

from src.db.connection import get_session_factory
from src.services.incident_history_service import IncidentHistoryService


async def search_incident_history(query: str, project_id: str = "") -> str:
    """Search historical incident records for similar past events.

    Args:
        query: The search query describing the current incident.
        project_id: Optional project ID to filter results.

    Returns:
        Formatted string with relevant historical incidents.
    """
    factory = get_session_factory()
    async with factory() as session:
        service = IncidentHistoryService(session=session)
        pid = uuid.UUID(project_id) if project_id else None
        results = await service.search(query=query, project_id=pid, limit=5)

    if not results:
        return "暂无相似历史事件。"

    sections = []
    for r in results:
        similarity = r.get("relevance_score", 1 - r["distance"])
        sections.append(
            f"### {r['title']} (相似度: {similarity:.2f})\n\n"
            f"{r['summary_md']}"
        )

    return "## 历史事件参考\n\n" + "\n\n---\n\n".join(sections)
