import asyncio
import uuid
from pathlib import Path

import orjson
from fastapi import APIRouter, BackgroundTasks, Depends, Request

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from src.api.schemas import (
    EventResponse,
    IncidentCreate,
    IncidentResponse,
    MessageResponse,
    PaginatedResponse,
    UserMessageRequest,
)
from src.db.connection import get_session, get_session_factory
from src.db.models import Attachment, Incident, Message
from src.lib.errors import BadRequestError, NotFoundError
from src.lib.logger import get_logger
from src.lib.paths import uploads_dir
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.services.agent_runner import AgentRunner
from src.services.incident_service import IncidentService
from src.services.notification_service import notify_fire_and_forget

log = get_logger(component="api")

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


async def _start_agent_background(
    runner: AgentRunner,
    incident_id: str,
    description: str,
    severity: str,
) -> None:
    sid = incident_id[:8]
    log.info("Background agent task starting", sid=sid)
    try:
        # Set status to investigating BEFORE starting agent
        # so the frontend sees the correct status on first query invalidation
        factory = get_session_factory()
        async with factory() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if incident:
                incident.status = "investigating"
                await session.commit()
                log.info("Status updated", sid=sid, status="investigating")
                notify_fire_and_forget(
                    "investigating", incident_id, description[:80],
                    severity=severity,
                )

        # Enrich description with parsed attachment content + collect images
        from src.lib.file_parsers import IMAGE_EXTENSIONS

        image_attachments: list[dict] = []
        async with factory() as session:
            result = await session.execute(
                select(Attachment)
                .where(Attachment.incident_id == uuid.UUID(incident_id))
            )
            for a in result.scalars():
                ext = Path(a.filename).suffix.lower()
                if ext in IMAGE_EXTENSIONS:
                    file_path = uploads_dir() / a.stored_filename
                    if file_path.exists():
                        image_attachments.append({
                            "filename": a.filename,
                            "bytes": file_path.read_bytes(),
                            "content_type": a.content_type,
                        })
                elif a.parsed_content:
                    description = f"{description}\n\n## 附件内容\n\n### 附件: {a.filename}\n\n{a.parsed_content}"

        thread_id = await runner.start(
            incident_id=incident_id,
            description=description,
            severity=severity,
            image_attachments=image_attachments,
        )
        # Write thread_id back after agent completes
        async with factory() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if incident:
                incident.thread_id = thread_id
                await session.commit()
                log.info("Thread ID saved", sid=sid, thread=thread_id)
    except Exception as e:
        log.error("Failed to start agent", incident_id=incident_id, error=str(e))
        # Publish error event to SSE channel
        try:
            channel = EventPublisher.channel_for_incident(incident_id)
            publisher = EventPublisher(get_redis())
            await publisher.publish(channel, "error", {
                "message": AgentRunner._format_agent_error(e),
            })
        except Exception:
            log.error("Failed to publish error event", incident_id=incident_id)
        # Update incident status to error
        try:
            factory = get_session_factory()
            async with factory() as err_session:
                incident = await err_session.get(Incident, uuid.UUID(incident_id))
                if incident:
                    incident.status = "error"
                    await err_session.commit()
        except Exception:
            log.error("Failed to update incident status to error", incident_id=incident_id)


@router.post("", response_model=IncidentResponse)
async def create_incident(
    body: IncidentCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    service = IncidentService(session=session)
    incident = await service.create(**body.model_dump())

    sid = str(incident.id)[:8]
    log.info("Incident created", sid=sid, severity=body.severity)

    # Start agent in background
    runner: AgentRunner = request.app.state.agent_runner
    background_tasks.add_task(
        _start_agent_background,
        runner,
        str(incident.id),
        body.description,
        body.severity,
    )

    notify_fire_and_forget(
        "open", str(incident.id), body.description[:80],
        severity=body.severity,
    )

    return incident


@router.get("", response_model=PaginatedResponse[IncidentResponse])
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_session),
):
    count_query = select(func.count()).select_from(Incident).where(Incident.is_archived == False)
    if status:
        count_query = count_query.where(Incident.status == status)
    if severity:
        count_query = count_query.where(Incident.severity == severity)
    total = await session.scalar(count_query) or 0

    query = select(Incident).options(selectinload(Incident.attachments)).where(Incident.is_archived == False).order_by(Incident.created_at.desc())
    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(query)
    items = list(result.scalars().all())

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


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


def _message_to_event(m: Message) -> dict:
    """Reconstruct SSE-compatible event dict from a persisted Message."""
    metadata = m.metadata_json if m.metadata_json else {}

    if m.event_type == "thinking":
        data = {"content": m.content, **metadata}
    elif m.event_type == "tool_use":
        data = metadata
    elif m.event_type == "tool_result":
        data = {"output": m.content, **metadata}
    elif m.event_type == "approval_required":
        data = metadata
    elif m.event_type == "ask_human":
        data = {"question": m.content}
    elif m.event_type == "done":
        data = {}
    elif m.event_type == "error":
        data = {"message": m.content}
    elif m.event_type == "approval_decided":
        data = metadata
    elif m.event_type == "user_message":
        data = {"content": m.content, **metadata}
    elif m.event_type == "skill_read":
        data = metadata or {"content": m.content}
    elif m.event_type == "skill_used":
        data = metadata
    elif m.event_type == "incident_stopped":
        data = {"reason": m.content}
    elif m.event_type == "agent_interrupted":
        data = {}
    elif m.event_type == "thinking_done":
        data = metadata  # {phase, agent}
    elif m.event_type == "answer":
        data = {"content": m.content}
    elif m.event_type == "answer_done":
        data = metadata or {}
    elif m.event_type == "agent_status":
        data = metadata  # {phase, agent, status}
    elif m.event_type == "confirm_resolution_required":
        data = metadata or {}
    elif m.event_type == "resolution_confirmed":
        data = {}
    else:
        data = {"content": m.content}

    return {
        "event_id": str(m.id),
        "event_type": m.event_type,
        "data": data,
        "timestamp": m.created_at.isoformat(),
    }


@router.get("/{incident_id}/events", response_model=list[EventResponse])
async def get_incident_events(
    incident_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Message)
        .where(Message.incident_id == incident_id)
        .order_by(Message.created_at)
    )
    return [_message_to_event(m) for m in result.scalars()]


@router.get("/{incident_id}/stream")
async def stream_incident(incident_id: uuid.UUID, since: str | None = None):
    redis = get_redis()
    channel = f"incident:{incident_id}"

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)  # Subscribe first to avoid gap
        last_ts = since or ""
        try:
            # 立即发送初始 keepalive，让客户端 onopen 即时触发
            yield {"comment": "connected"}

            # Replay events from DB that occurred after `since`
            if since:
                from datetime import datetime

                since_dt = datetime.fromisoformat(since)
                factory = get_session_factory()
                async with factory() as session:
                    result = await session.execute(
                        select(Message)
                        .where(Message.incident_id == incident_id)
                        .where(Message.created_at > since_dt)
                        .order_by(Message.created_at)
                    )
                    for m in result.scalars():
                        evt = _message_to_event(m)
                        evt["replay"] = True
                        last_ts = evt["timestamp"]
                        yield {"data": orjson.dumps(evt).decode()}

            # Real-time mode: forward Redis pubsub messages, dedup against replayed events
            idle_seconds = 0.0
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    idle_seconds = 0.0
                    if last_ts:
                        try:
                            parsed = orjson.loads(msg["data"])
                            if parsed.get("timestamp", "") <= last_ts:
                                continue
                            last_ts = parsed["timestamp"]
                        except Exception:
                            pass
                    yield {"data": msg["data"]}
                else:
                    idle_seconds += 0.1
                    if idle_seconds >= 15:
                        yield {"comment": "keepalive"}
                        idle_seconds = 0.0
                    await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return EventSourceResponse(event_generator())


@router.post("/{incident_id}/messages", response_model=MessageResponse)
async def send_user_message(
    incident_id: uuid.UUID,
    body: UserMessageRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    incident = await session.get(Incident, incident_id)
    if not incident:
        raise NotFoundError("Incident not found")

    from src.lib.file_parsers import IMAGE_EXTENSIONS

    metadata = {}
    attachment_texts: list[str] = []
    msg_image_attachments: list[dict] = []
    if body.attachment_ids:
        result = await session.execute(
            select(Attachment).where(Attachment.id.in_(body.attachment_ids))
        )
        attachments_list = list(result.scalars())
        for attachment in attachments_list:
            attachment.incident_id = incident_id
            ext = Path(attachment.filename).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                file_path = uploads_dir() / attachment.stored_filename
                if file_path.exists():
                    msg_image_attachments.append({
                        "filename": attachment.filename,
                        "bytes": file_path.read_bytes(),
                        "content_type": attachment.content_type,
                    })
            elif attachment.parsed_content:
                attachment_texts.append(f"[附件: {attachment.filename}]\n{attachment.parsed_content}")
        await session.flush()

        metadata["attachment_ids"] = [str(aid) for aid in body.attachment_ids]
        metadata["attachments_meta"] = [
            {
                "id": str(a.id),
                "filename": a.filename,
                "content_type": a.content_type,
                "size": a.size,
            }
            for a in attachments_list
        ]

    service = IncidentService(session=session)
    message = await service.save_message(
        incident_id=incident_id,
        role="user",
        event_type="user_message",
        content=body.content,
        metadata_json=metadata if metadata else None,
    )

    # Enrich human input with parsed attachment content
    human_input = body.content
    if attachment_texts:
        human_input += "\n\n## 附件内容\n\n" + "\n\n---\n\n".join(attachment_texts)

    # If agent is waiting for human input (ask_human interrupt), resume the graph
    if incident.thread_id and incident.status == "investigating":
        sid = str(incident.id)[:8]
        log.info("User message received, resuming agent", sid=sid)
        log.debug("User message content", sid=sid, content=body.content)

        # Clear stale cancel flags before resuming
        redis = get_redis()
        await redis.delete(f"incident:{incident_id}:cancel")

        runner: AgentRunner = request.app.state.agent_runner
        background_tasks.add_task(
            runner.resume_with_human_input,
            thread_id=incident.thread_id,
            incident_id=str(incident.id),
            human_input=human_input,
            image_attachments=msg_image_attachments,
        )

    # If agent was interrupted by user, resume after interrupt
    elif incident.thread_id and incident.status == "interrupted":
        sid = str(incident.id)[:8]
        log.info("User message received (interrupted), resuming agent", sid=sid)

        incident.status = "investigating"
        await session.commit()

        # Clear stale cancel flags before resuming
        redis = get_redis()
        await redis.delete(f"incident:{incident_id}:cancel")

        runner: AgentRunner = request.app.state.agent_runner
        background_tasks.add_task(
            runner.resume_after_interrupt,
            thread_id=incident.thread_id,
            incident_id=str(incident.id),
            human_input=human_input,
            image_attachments=msg_image_attachments,
        )

    return message



@router.post("/{incident_id}/confirm-resolution")
async def confirm_resolution(
    incident_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    incident = await session.get(Incident, incident_id)
    if not incident:
        raise NotFoundError("Incident not found")
    if incident.status != "investigating":
        raise BadRequestError("Incident is not in investigating state")

    # Publish resolution_confirmed event (persist + SSE)
    channel = EventPublisher.channel_for_incident(str(incident_id))
    runner: AgentRunner = request.app.state.agent_runner
    await runner.publisher.publish(channel, "resolution_confirmed", {})

    # Resume agent with "confirmed" input
    if incident.thread_id:
        sid = str(incident.id)[:8]
        log.info("Resolution confirmed, resuming agent", sid=sid)
        background_tasks.add_task(
            runner.resume_with_human_input,
            thread_id=incident.thread_id,
            incident_id=str(incident.id),
            human_input="confirmed",
        )

    return {"status": "ok"}


@router.post("/{incident_id}/interrupt")
async def interrupt_incident(
    incident_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Interrupt a running agent so the user can provide guidance."""
    incident = await session.get(Incident, incident_id)
    if not incident:
        raise NotFoundError("Incident not found")
    if incident.status != "investigating":
        raise BadRequestError("Incident is not in investigating state")

    redis = get_redis()
    sid = str(incident_id)[:8]

    # Check if agent is paused at a LangGraph interrupt point (not actively streaming).
    # If so, handle interrupt immediately instead of relying on the streaming loop.
    if incident.thread_id:
        runner: AgentRunner = request.app.state.agent_runner
        config = {"configurable": {"thread_id": incident.thread_id}}
        state = await runner.graph.aget_state(config)
        if state.next:
            # Agent is paused (human_approval / ask_human / confirm_resolution)
            incident.status = "interrupted"
            await session.commit()

            channel = EventPublisher.channel_for_incident(str(incident_id))
            await runner.publisher.publish(channel, "agent_interrupted", {})

            log.info("Incident interrupted (agent was paused)", sid=sid, paused_at=state.next)
            return {"status": "ok"}

    # Agent is actively streaming — set Redis flag for the streaming loop to pick up
    await redis.set(f"incident:{incident_id}:cancel", "interrupted", ex=300)

    log.info("Incident interrupt requested", sid=sid)

    return {"status": "ok"}


@router.post("/{incident_id}/stop", response_model=IncidentResponse)
async def stop_incident(
    incident_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    incident = await session.get(Incident, incident_id)
    if not incident:
        raise NotFoundError("Incident not found")
    if incident.status not in ("open", "investigating", "interrupted"):
        raise BadRequestError("Incident is not active")

    # Set Redis cancel flag
    redis = get_redis()
    await redis.set(f"incident:{incident_id}:cancel", "stopped", ex=300)

    # Update DB status
    incident.status = "stopped"
    await session.commit()

    sid = str(incident_id)[:8]
    log.info("Incident stopped", sid=sid)

    # Publish SSE event
    runner: AgentRunner = request.app.state.agent_runner
    channel = EventPublisher.channel_for_incident(str(incident_id))
    await runner.publisher.publish(channel, "incident_stopped", {"reason": "stopped"})

    notify_fire_and_forget(
        "stopped", str(incident_id), incident.summary_title or incident.description[:80],
        severity=incident.severity or "",
    )

    # Re-fetch with all columns and attachments to avoid lazy-load MissingGreenlet
    result = await session.execute(
        select(Incident).options(selectinload(Incident.attachments)).where(Incident.id == incident_id)
    )
    return result.scalar_one()


@router.post("/{incident_id}/archive", response_model=IncidentResponse)
async def archive_incident(
    incident_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Incident).options(selectinload(Incident.attachments)).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundError("Incident not found")

    incident.is_archived = True
    await session.commit()

    sid = str(incident_id)[:8]
    log.info("Incident archived", sid=sid)

    await session.refresh(incident)
    return incident
