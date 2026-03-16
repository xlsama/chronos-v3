import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Connection, Project, Service, ServiceConnectionBinding, ServiceDependency


class TopologyService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project_topology(self, project_id: uuid.UUID) -> dict | None:
        project = await self.session.get(Project, project_id)
        if not project:
            return None

        service_result = await self.session.execute(
            select(Service).where(Service.project_id == project_id).order_by(Service.name)
        )
        connection_result = await self.session.execute(
            select(Connection).where(Connection.project_id == project_id).order_by(Connection.name)
        )
        dependency_result = await self.session.execute(
            select(ServiceDependency)
            .where(ServiceDependency.project_id == project_id)
            .order_by(ServiceDependency.created_at.desc())
        )
        binding_result = await self.session.execute(
            select(ServiceConnectionBinding)
            .where(ServiceConnectionBinding.project_id == project_id)
            .order_by(ServiceConnectionBinding.priority.asc(), ServiceConnectionBinding.created_at.desc())
        )

        return {
            "project": project,
            "services": list(service_result.scalars().all()),
            "dependencies": list(dependency_result.scalars().all()),
            "connections": list(connection_result.scalars().all()),
            "bindings": list(binding_result.scalars().all()),
        }
