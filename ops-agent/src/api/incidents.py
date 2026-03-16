import asyncio
import uuid

import orjson
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from src.api.schemas import (
    IncidentCreate,
    IncidentResponse,
    MessageResponse,
    UserMessageRequest,
)
from src.config import get_settings
from src.db.connection import get_session, get_session_factory
from src.db.models import Attachment, Incident, Message
from src.lib.errors import NotFoundError
from src.lib.logger import logger
from src.lib.redis import get_redis
from src.services.agent_runner import AgentRunner
from src.services.incident_history_service import IncidentHistoryService
from src.services.incident_service import IncidentService

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


async def _start_agent_background(
    runner: AgentRunner,
    incident_id: str,
    title: str,
    description: str,
    severity: str,
    infrastructure_id: str,
    project_id: str,
) -> None:
    try:
        thread_id = await runner.start(
            incident_id=incident_id,
            title=title,
            description=description,
            severity=severity,
            infrastructure_id=infrastructure_id,
            project_id=project_id,
        )
        # Write thread_id back + set status to investigating
        factory = get_session_factory()
        async with factory() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if incident:
                incident.thread_id = thread_id
                incident.status = "investigating"
                await session.commit()
                logger.info(f"Agent started for incident {incident_id}, thread {thread_id}")
    except Exception as e:
        logger.error(f"Failed to start agent for incident {incident_id}: {e}")


@router.post("", response_model=IncidentResponse)
async def create_incident(
    body: IncidentCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    service = IncidentService(session=session)
    incident = await service.create(**body.model_dump())

    # Start agent in background
    runner: AgentRunner = request.app.state.agent_runner
    background_tasks.add_task(
        _start_agent_background,
        runner,
        str(incident.id),
        incident.title,
        body.description,
        body.severity,
        str(body.infrastructure_id or ""),
        str(body.project_id or ""),
    )

    return incident


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_session),
):
    query = select(Incident).options(selectinload(Incident.attachments)).order_by(Incident.created_at.desc())
    if status:
        query = query.where(Incident.status == status)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Incident).options(selectinload(Incident.attachments)).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundError("Incident not found")
    return incident


@router.get("/{incident_id}/messages", response_model=list[MessageResponse])
async def get_incident_messages(
    incident_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Message)
        .where(Message.incident_id == incident_id)
        .order_by(Message.created_at)
    )
    return result.scalars().all()


@router.get("/{incident_id}/stream")
async def stream_incident(incident_id: uuid.UUID):
    redis = get_redis()
    channel = f"incident:{incident_id}"

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    yield {"data": msg["data"]}
                else:
                    await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return EventSourceResponse(event_generator())


@router.post("/{incident_id}/messages")
async def send_user_message(
    incident_id: uuid.UUID,
    body: UserMessageRequest,
    session: AsyncSession = Depends(get_session),
):
    incident = await session.get(Incident, incident_id)
    if not incident:
        raise NotFoundError("Incident not found")

    if body.attachment_ids:
        result = await session.execute(
            select(Attachment).where(Attachment.id.in_(body.attachment_ids))
        )
        for attachment in result.scalars():
            attachment.incident_id = incident_id
        await session.flush()

    service = IncidentService(session=session)
    message = await service.save_message(
        incident_id=incident_id,
        role="user",
        event_type="user_message",
        content=body.content,
    )
    return {"ok": True, "message_id": str(message.id)}


@router.post("/{incident_id}/save-to-memory")
async def save_to_memory(
    incident_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    incident = await session.get(Incident, incident_id)
    if not incident:
        raise NotFoundError("Incident not found")

    if incident.saved_to_memory:
        return {"ok": False, "error": "already_saved"}

    if not incident.summary_md:
        return {"ok": False, "error": "no_summary"}

    service = IncidentHistoryService(session=session)
    record = await service.save(
        incident_id=incident.id,
        project_id=incident.project_id,
        title=incident.title,
        summary_md=incident.summary_md,
    )

    return {"ok": True, "incident_history_id": str(record.id)}
