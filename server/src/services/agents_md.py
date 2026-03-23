from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ProjectDocument
from src.lib.paths import knowledge_dir


async def ensure_agents_md(
    session: AsyncSession,
    project_id,
    project_name: str,
    project_slug: str,
) -> ProjectDocument | None:
    """Ensure the project has an AGENTS.md document (empty content, not indexed)."""
    existing = (
        await session.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.doc_type == "agents_config",
            )
        )
    ).scalar_one_or_none()

    if existing:
        return None

    doc = ProjectDocument(
        project_id=project_id,
        filename="AGENTS.md",
        content="",
        doc_type="agents_config",
        status="indexed",
    )
    session.add(doc)
    await session.flush()

    # Write empty file to disk
    storage_dir = knowledge_dir(project_slug)
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / "AGENTS.md").write_text("", encoding="utf-8")

    return doc
