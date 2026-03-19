import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ContentVersion


class VersionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_version(
        self,
        entity_type: str,
        entity_id: str,
        content: str,
        change_source: str = "manual",
    ) -> ContentVersion:
        """保存新版本。自动计算 version_number（当前最大 + 1），内容相同则跳过"""
        # 去重：如果最新版本内容相同，跳过
        latest_result = await self.session.execute(
            select(ContentVersion)
            .where(
                ContentVersion.entity_type == entity_type,
                ContentVersion.entity_id == entity_id,
            )
            .order_by(ContentVersion.version_number.desc())
            .limit(1)
        )
        latest_version = latest_result.scalar()
        if latest_version and latest_version.content == content:
            return latest_version

        max_version = latest_version.version_number if latest_version else 0

        version = ContentVersion(
            entity_type=entity_type,
            entity_id=entity_id,
            content=content,
            version_number=max_version + 1,
            change_source=change_source,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def list_versions(
        self, entity_type: str, entity_id: str
    ) -> list[ContentVersion]:
        """按 version_number DESC 返回所有版本"""
        result = await self.session.execute(
            select(ContentVersion)
            .where(
                ContentVersion.entity_type == entity_type,
                ContentVersion.entity_id == entity_id,
            )
            .order_by(ContentVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_version(self, version_id: uuid.UUID) -> ContentVersion | None:
        """获取单个版本"""
        return await self.session.get(ContentVersion, version_id)
