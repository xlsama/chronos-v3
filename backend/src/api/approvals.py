import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ApprovalDecisionRequest, ApprovalResponse
from src.db.connection import get_session
from src.db.models import ApprovalRequest, Incident
from src.lib.errors import ConflictError, NotFoundError, ValidationError
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.services.approval_service import ApprovalService

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    approval = await session.get(ApprovalRequest, approval_id)
    if not approval:
        raise NotFoundError("Approval request not found")
    return approval


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    if body.decision not in ("approved", "rejected"):
        raise ValidationError("Decision must be 'approved' or 'rejected'")

    service = ApprovalService(session=session)
    try:
        approval = await service.decide(approval_id, decision=body.decision, decided_by=body.decided_by)
    except ValueError as e:
        msg = str(e)
        if "already decided" in msg:
            raise ConflictError(msg)
        raise NotFoundError(msg)

    # Publish approval_decided SSE event
    redis = get_redis()
    try:
        publisher = EventPublisher(redis)
        channel = EventPublisher.channel_for_incident(str(approval.incident_id))
        await publisher.publish(
            channel=channel,
            event_type="approval_decided",
            data={
                "approval_id": str(approval.id),
                "decision": body.decision,
                "decided_by": body.decided_by,
            },
        )
    finally:
        await redis.aclose()

    # Resume graph if approved
    if body.decision == "approved":
        incident = await session.get(Incident, approval.incident_id)
        if incident and incident.thread_id:
            runner = request.app.state.agent_runner
            background_tasks.add_task(
                runner.resume,
                thread_id=incident.thread_id,
                incident_id=str(incident.id),
                approval_result={"decision": "approved"},
            )

    return approval
