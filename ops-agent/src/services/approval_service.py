import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ApprovalRequest


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
    ) -> ApprovalRequest:
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
        approval: ApprovalRequest,
        decision: str,
        decided_by: str,
    ) -> ApprovalRequest:
        if approval.decision is not None:
            raise ValueError(f"Approval request already decided: {approval.decision}")

        approval.decision = decision
        approval.decided_by = decided_by
        approval.decided_at = datetime.now(timezone.utc)
        await self.session.commit()
        return approval
