import uuid

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import MonitoringSource
from src.services.crypto import CryptoService


class MonitoringSourceService:
    def __init__(self, session: AsyncSession, crypto: CryptoService):
        self.session = session
        self.crypto = crypto

    async def create(
        self,
        project_id: uuid.UUID,
        name: str,
        source_type: str,
        endpoint: str,
        auth_header: str | None = None,
    ) -> MonitoringSource:
        conn_config = None
        if auth_header:
            config_data = {"auth_header": auth_header}
            conn_config = self.crypto.encrypt(orjson.dumps(config_data).decode())

        source = MonitoringSource(
            project_id=project_id,
            name=name,
            source_type=source_type,
            endpoint=endpoint,
            conn_config=conn_config,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def list_by_project(self, project_id: uuid.UUID) -> list[MonitoringSource]:
        result = await self.session.execute(
            select(MonitoringSource)
            .where(MonitoringSource.project_id == project_id)
            .order_by(MonitoringSource.name)
        )
        return list(result.scalars().all())

    async def get(self, source_id: uuid.UUID) -> MonitoringSource | None:
        return await self.session.get(MonitoringSource, source_id)

    async def delete(self, source_id: uuid.UUID) -> bool:
        source = await self.session.get(MonitoringSource, source_id)
        if not source:
            return False
        await self.session.delete(source)
        await self.session.commit()
        return True

    async def get_by_project_and_type(
        self, project_id: uuid.UUID, source_type: str
    ) -> MonitoringSource | None:
        result = await self.session.execute(
            select(MonitoringSource).where(
                MonitoringSource.project_id == project_id,
                MonitoringSource.source_type == source_type,
            )
        )
        return result.scalar_one_or_none()

    async def has_source_types(self, project_id: uuid.UUID) -> tuple[bool, bool]:
        """Check if project has Prometheus and/or Loki sources."""
        sources = await self.list_by_project(project_id)
        types = {s.source_type for s in sources}
        return "prometheus" in types, "loki" in types
