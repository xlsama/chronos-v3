import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ApprovalDecisionRequest, ApprovalResponse
from src.db.connection import get_session
from src.db.models import ApprovalRequest, Incident
from src.lib.errors import BadRequestError, NotFoundError
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
    # Check if the incident is still active before deciding
    approval_record = await session.get(ApprovalRequest, approval_id)
    if not approval_record:
        raise NotFoundError("Approval request not found")
    incident = await session.get(Incident, approval_record.incident_id)
    if incident and incident.status in ("stopped", "resolved", "interrupted"):
        raise BadRequestError("事件已终止，无法审批")

    service = ApprovalService(session=session)
    approval = await service.decide(approval_id, decision=body.decision, decided_by=body.decided_by)

    # Publish approval_decided SSE event (use app-level publisher for persistence)
    publisher = request.app.state.agent_runner.publisher
    channel = EventPublisher.channel_for_incident(str(approval.incident_id))
    decided_data: dict = {
        "approval_id": str(approval.id),
        "decision": body.decision,
        "decided_by": body.decided_by,
    }
    if body.supplement_text:
        decided_data["supplement_text"] = body.supplement_text
    await publisher.publish(
        channel=channel,
        event_type="approval_decided",
        data=decided_data,
    )

    # Resume graph for all decisions (approved / rejected / supplemented)
    if incident and incident.thread_id:
        # Clear stale cancel flags before resuming to prevent old interrupt
        # requests from immediately cancelling the new run
        from src.lib.redis import get_redis
        redis = get_redis()
        await redis.delete(f"incident:{approval.incident_id}:cancel")

        approval_result: dict = {"decision": body.decision}
        if body.supplement_text:
            approval_result["supplement_text"] = body.supplement_text

        runner = request.app.state.agent_runner
        background_tasks.add_task(
            runner.resume,
            thread_id=incident.thread_id,
            incident_id=str(incident.id),
            approval_result=approval_result,
        )

    return approval
