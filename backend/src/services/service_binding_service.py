import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ServiceConnectionBinding


class ServiceBindingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        project_id: uuid.UUID,
        service_id: uuid.UUID,
        connection_id: uuid.UUID,
        usage_type: str = "runtime_inspect",
        priority: int = 100,
        notes: str | None = None,
    ) -> ServiceConnectionBinding:
        binding = ServiceConnectionBinding(
            project_id=project_id,
            service_id=service_id,
            connection_id=connection_id,
            usage_type=usage_type,
            priority=priority,
            notes=notes,
        )
        self.session.add(binding)
        await self.session.commit()
        await self.session.refresh(binding)
        return binding

    async def list_by_project(self, project_id: uuid.UUID) -> list[ServiceConnectionBinding]:
        result = await self.session.execute(
            select(ServiceConnectionBinding)
            .where(ServiceConnectionBinding.project_id == project_id)
            .order_by(ServiceConnectionBinding.priority.asc(), ServiceConnectionBinding.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, binding_id: uuid.UUID) -> ServiceConnectionBinding | None:
        return await self.session.get(ServiceConnectionBinding, binding_id)

    async def delete(self, binding_id: uuid.UUID) -> bool:
        binding = await self.session.get(ServiceConnectionBinding, binding_id)
        if not binding:
            return False
        await self.session.delete(binding)
        await self.session.commit()
        return True
