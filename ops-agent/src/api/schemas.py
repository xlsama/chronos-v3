import uuid
from datetime import datetime

from pydantic import BaseModel


# ── Infrastructure ──

class InfrastructureCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str = "root"
    password: str | None = None
    private_key: str | None = None
    project_id: uuid.UUID | None = None


class InfrastructureResponse(BaseModel):
    id: uuid.UUID
    name: str
    host: str
    port: int
    username: str
    status: str
    project_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str


# ── Incident ──

class IncidentCreate(BaseModel):
    title: str
    description: str
    severity: str = "medium"
    infrastructure_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class IncidentResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    status: str
    severity: str
    infrastructure_id: uuid.UUID | None
    project_id: uuid.UUID | None
    summary_md: str | None
    thread_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    role: str
    event_type: str
    content: str
    metadata_json: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserMessageRequest(BaseModel):
    content: str


# ── Approval ──

class ApprovalResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    tool_name: str
    tool_args: str
    decision: str | None
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecisionRequest(BaseModel):
    decision: str  # "approved" or "rejected"
    decided_by: str = "admin"
