import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Project


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        service_md: str | None = None,
    ) -> Project:
        if not slug:
            slug = self._generate_slug(name)

        project = Project(
            name=name,
            slug=slug,
            description=description,
            service_md=service_md,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get(self, project_id: uuid.UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_by_slug(self, slug: str) -> Project | None:
        result = await self.session.execute(select(Project).where(Project.slug == slug))
        return result.scalar_one_or_none()

    async def list(self) -> list[Project]:
        result = await self.session.execute(select(Project).order_by(Project.created_at.desc()))
        return list(result.scalars().all())

    async def update(self, project: Project, **kwargs) -> Project:
        for key, value in kwargs.items():
            if value is not None and hasattr(project, key):
                setattr(project, key, value)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def update_service_md(self, project: Project, service_md: str) -> Project:
        project.service_md = service_md
        await self.session.commit()
        await self.session.refresh(project)
        return project

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
