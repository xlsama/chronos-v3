import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Incident, IncidentHistory
from src.lib.embedder import Embedder

HISTORY_DIR = Path(__file__).parent.parent.parent / "incident_history"


class IncidentHistoryService:
    def __init__(self, session: AsyncSession, embedder: Embedder | None = None):
        self.session = session
        self.embedder = embedder or Embedder()

    async def save(
        self,
        incident_id: uuid.UUID,
        project_id: uuid.UUID | None,
        title: str,
        summary_md: str,
    ) -> IncidentHistory:
        embedding = await self.embedder.embed_text(summary_md)

        record = IncidentHistory(
            incident_id=incident_id,
            project_id=project_id,
            title=title,
            summary_md=summary_md,
            embedding=embedding,
        )
        self.session.add(record)

        # Update incident.saved_to_memory
        incident = await self.session.get(Incident, incident_id)
        if incident:
            incident.saved_to_memory = True

        await self.session.commit()
        await self.session.refresh(record)

        # Write markdown file
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{str(record.id)[:8]}_{title[:40].replace('/', '_')}.md"
        (HISTORY_DIR / filename).write_text(summary_md, encoding="utf-8")

        return record

    async def search(
        self,
        query: str,
        project_id: uuid.UUID | None = None,
        limit: int = 5,
    ) -> list[dict]:
        query_embedding = await self.embedder.embed_text(query)

        stmt = (
            select(
                IncidentHistory.title,
                IncidentHistory.summary_md,
                IncidentHistory.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(IncidentHistory.embedding.isnot(None))
            .order_by("distance")
            .limit(limit)
        )

        if project_id:
            stmt = stmt.where(IncidentHistory.project_id == project_id)

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "title": row.title,
                "summary_md": row.summary_md,
                "distance": row.distance,
            }
            for row in rows
        ]
