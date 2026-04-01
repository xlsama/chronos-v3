import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ApprovalRequest
from src.lib.errors import ApprovalAlreadyDecidedError, ApprovalNotFoundError, ValidationError


class ApprovalService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        incident_id: uuid.UUID,
        tool_name: str,
        tool_args: str,
        risk_level: str | None = None,
        risk_detail: str | None = None,
        explanation: str | None = None,
        require_explanation: bool = False,
    ) -> ApprovalRequest:
        explanation = explanation.strip() if explanation else None
        if require_explanation and not explanation:
            raise ValidationError("需审批的工具调用必须提供 explanation 说明")

        approval = ApprovalRequest(
            incident_id=incident_id,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level=risk_level,
            risk_detail=risk_detail,
            explanation=explanation,
        )
        self.session.add(approval)
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def decide(
        self,
        approval_id: uuid.UUID,
        decision: str,
        decided_by: str,
    ) -> ApprovalRequest:
        stmt = select(ApprovalRequest).where(ApprovalRequest.id == approval_id).with_for_update()
        result = await self.session.execute(stmt)
        approval = result.scalar_one_or_none()
        if approval is None:
            raise ApprovalNotFoundError()

        if approval.decision is not None:
            raise ApprovalAlreadyDecidedError(
                f"Approval request already decided: {approval.decision}"
            )

        approval.decision = decision
        approval.decided_by = decided_by
        approval.decided_at = datetime.now(timezone.utc)
        await self.session.commit()
        return approval
