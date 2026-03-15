import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Incident, Message


class IncidentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        title: str,
        description: str,
        severity: str = "medium",
        infrastructure_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> Incident:
        incident = Incident(
            title=title,
            description=description,
            status="open",
            severity=severity,
            infrastructure_id=infrastructure_id,
            project_id=project_id,
        )
        self.session.add(incident)
        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def update_status(self, incident: Incident, status: str) -> Incident:
        incident.status = status
        await self.session.commit()
        return incident

    async def set_summary(self, incident: Incident, summary_md: str) -> Incident:
        incident.summary_md = summary_md
        incident.status = "resolved"
        await self.session.commit()
        return incident

    async def save_message(
        self,
        incident_id: uuid.UUID,
        role: str,
        event_type: str,
        content: str,
        metadata_json: str | None = None,
    ) -> Message:
        message = Message(
            incident_id=incident_id,
            role=role,
            event_type=event_type,
            content=content,
            metadata_json=metadata_json,
        )
        self.session.add(message)
        await self.session.commit()
        return message
