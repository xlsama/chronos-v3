import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ApprovalDecisionRequest, ApprovalResponse
from src.db.connection import get_session
from src.db.models import ApprovalRequest
from src.lib.errors import NotFoundError, ValidationError
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
    session: AsyncSession = Depends(get_session),
):
    approval = await session.get(ApprovalRequest, approval_id)
    if not approval:
        raise NotFoundError("Approval request not found")

    if body.decision not in ("approved", "rejected"):
        raise ValidationError("Decision must be 'approved' or 'rejected'")

    service = ApprovalService(session=session)
    try:
        approval = await service.decide(approval, decision=body.decision, decided_by=body.decided_by)
    except ValueError as e:
        raise ValidationError(str(e))

    # TODO: Resume graph if approved (Phase 1 integration)

    return approval
