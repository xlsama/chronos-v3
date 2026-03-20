import time

from src.db.connection import get_session_factory
from src.lib.logger import get_logger
from src.services.incident_history_service import IncidentHistoryService

log = get_logger(component="history")


async def search_incident_history(query: str) -> tuple[str, list[dict]]:
    """Search historical incident records for similar past events.

    Args:
        query: The search query describing the current incident.

    Returns:
        Tuple of (formatted text, sources list).
    """
    t0 = time.monotonic()
    log.info("search_incident_history", query_len=len(query))
    log.debug("search_incident_history", query=query)
    factory = get_session_factory()
    async with factory() as session:
        service = IncidentHistoryService(session=session)
        results = await service.search(query=query, limit=3)

    elapsed = time.monotonic() - t0
    log.info("search_incident_history completed", elapsed=f"{elapsed:.2f}s", result_count=len(results))

    if not results:
        return ("暂无相似历史事件。", [])

    sources = [
        {"type": "incident_history", "id": r["id"], "title": r["title"]}
        for r in results
    ]

    sections = []
    for r in results:
        similarity = r.get("relevance_score", 1 - r["distance"])
        sections.append(
            f"### {r['title']} (相似度: {similarity:.2f})\n\n"
            f"{r['summary_md']}"
        )

    text = "## 历史事件参考\n\n" + "\n\n---\n\n".join(sections)
    return (text, sources)
