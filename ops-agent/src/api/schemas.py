import uuid
from datetime import datetime

from pydantic import BaseModel


# ── Infrastructure ──

class InfrastructureCreate(BaseModel):
    name: str
    type: str = "ssh"  # ssh, kubernetes
    # SSH fields
    host: str = ""
    port: int = 22
    username: str = "root"
    password: str | None = None
    private_key: str | None = None
    # K8s fields
    kubeconfig: str | None = None
    context: str | None = None
    namespace: str | None = None
    project_id: uuid.UUID | None = None


class InfrastructureResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
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


# ── Service ──

class ServiceCreate(BaseModel):
    infrastructure_id: uuid.UUID
    name: str
    service_type: str
    port: int | None = None
    namespace: str | None = None
    config_json: str | None = None


class ServiceResponse(BaseModel):
    id: uuid.UUID
    infrastructure_id: uuid.UUID
    name: str
    service_type: str
    port: int | None
    namespace: str | None
    config_json: str | None
    status: str
    discovery_method: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscoverServicesResponse(BaseModel):
    discovered: int
    services: list[ServiceResponse]


# ── MonitoringSource ──

class MonitoringSourceCreate(BaseModel):
    project_id: uuid.UUID
    name: str
    source_type: str  # prometheus, loki
    endpoint: str
    auth_header: str | None = None  # e.g. "Bearer xxx"


class MonitoringSourceResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    source_type: str
    endpoint: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Incident ──

class IncidentCreate(BaseModel):
    title: str = ""
    description: str
    severity: str = "medium"
    infrastructure_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    attachment_ids: list[uuid.UUID] = []


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID | None
    filename: str
    stored_filename: str
    content_type: str
    size: int
    created_at: datetime

    model_config = {"from_attributes": True}


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
    saved_to_memory: bool
    attachments: list[AttachmentResponse] = []
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
    attachment_ids: list[uuid.UUID] = []


# ── Approval ──

class ApprovalResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    tool_name: str
    tool_args: str
    decision: str | None
    decided_by: str | None
    decided_at: datetime | None
    risk_level: str | None
    risk_detail: str | None
    explanation: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecisionRequest(BaseModel):
    decision: str  # "approved" or "rejected"
    decided_by: str = "admin"


# ── Project ──

class ProjectCreate(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    cloud_md: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None


class ProjectCloudMdUpdate(BaseModel):
    cloud_md: str


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    cloud_md: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Document ──

class DocumentUpload(BaseModel):
    filename: str
    content: str
    doc_type: str = "markdown"


class DocumentResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    doc_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
