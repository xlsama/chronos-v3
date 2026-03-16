import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Service, ServiceDependency
from src.lib.errors import ValidationError


class ServiceDependencyService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        project_id: uuid.UUID,
        from_service_id: uuid.UUID,
        to_service_id: uuid.UUID,
        dependency_type: str = "api_call",
        description: str | None = None,
        confidence: int = 100,
    ) -> ServiceDependency:
        from_service = await self.session.get(Service, from_service_id)
        to_service = await self.session.get(Service, to_service_id)
        if not from_service or not to_service:
            raise ValidationError("Service dependency references unknown service")
        if from_service.project_id != project_id or to_service.project_id != project_id:
            raise ValidationError("Service dependency must stay inside one project")
        if from_service_id == to_service_id:
            raise ValidationError("Service cannot depend on itself")

        existing = (
            await self.session.execute(
                select(ServiceDependency).where(
                    ServiceDependency.project_id == project_id,
                    ServiceDependency.from_service_id == from_service_id,
                    ServiceDependency.to_service_id == to_service_id,
                    ServiceDependency.dependency_type == dependency_type,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise ValidationError("Service dependency already exists")

        dependency = ServiceDependency(
            project_id=project_id,
            from_service_id=from_service_id,
            to_service_id=to_service_id,
            dependency_type=dependency_type,
            description=description,
            confidence=confidence,
        )
        self.session.add(dependency)
        await self.session.commit()
        await self.session.refresh(dependency)
        return dependency

    async def list_by_project(self, project_id: uuid.UUID) -> list[ServiceDependency]:
        result = await self.session.execute(
            select(ServiceDependency)
            .where(ServiceDependency.project_id == project_id)
            .order_by(ServiceDependency.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, dependency_id: uuid.UUID) -> ServiceDependency | None:
        return await self.session.get(ServiceDependency, dependency_id)

    async def delete(self, dependency_id: uuid.UUID) -> bool:
        dependency = await self.session.get(ServiceDependency, dependency_id)
        if not dependency:
            return False
        await self.session.delete(dependency)
        await self.session.commit()
        return True
