import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Project, ProjectServer


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        name: str,
        slug: str | None = None,
        description: str | None = None,
    ) -> Project:
        if not slug:
            slug = self._generate_slug(name)

        project = Project(
            name=name,
            slug=slug,
            description=description,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project, ["project_servers"])
        return project

    async def get(self, project_id: uuid.UUID) -> Project | None:
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.project_servers))
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Project | None:
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.project_servers))
            .where(Project.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Project]:
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.project_servers))
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, project: Project, **kwargs) -> Project:
        for key, value in kwargs.items():
            if key == "linked_server_ids":
                continue  # handled separately via set_linked_servers
            if value is not None and hasattr(project, key):
                setattr(project, key, value)
        await self.session.commit()
        await self.session.refresh(project, ["project_servers"])
        return project

    async def set_linked_servers(self, project: Project, server_ids: list[uuid.UUID]) -> None:
        """Replace linked servers via the junction table."""
        # Clear existing
        for ps in list(project.project_servers):
            await self.session.delete(ps)
        await self.session.flush()

        # Add new
        for sid in server_ids:
            self.session.add(ProjectServer(project_id=project.id, server_id=sid))
        await self.session.commit()
        await self.session.refresh(project, ["project_servers"])

    async def delete(self, project: Project) -> None:
        await self.session.delete(project)
        await self.session.commit()

    @staticmethod
    def _generate_slug(name: str) -> str:
        slug = name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")
