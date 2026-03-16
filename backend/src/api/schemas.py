import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field


class ProjectCreate(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionCreate(BaseModel):
    name: str
    type: Literal["ssh", "kubernetes"] = "ssh"
    description: str | None = None
    host: str = ""
    port: int = 22
    username: str = "root"
    password: str | None = None
    private_key: str | None = None
    kubeconfig: str | None = None
    context: str | None = None
    namespace: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    scope_metadata: dict[str, Any] = Field(default_factory=dict)
    project_id: uuid.UUID


class ConnectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class ConnectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    description: str | None
    host: str
    port: int
    username: str
    status: str
    capabilities: list[str]
    scope_metadata: dict[str, Any]
    project_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str


class ServiceCreate(BaseModel):
    project_id: uuid.UUID
    name: str
    slug: str | None = None
    service_type: str = "custom"
    description: str | None = None
    business_context: str | None = None
    owner: str | None = None
    keywords: list[str] = Field(default_factory=list)
    status: str = "unknown"
    source: str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    service_type: str | None = None
    description: str | None = None
    business_context: str | None = None
    owner: str | None = None
    keywords: list[str] | None = None
    status: str | None = None
    source: str | None = None
    metadata: dict[str, Any] | None = None


class ServiceResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    slug: str
    service_type: str
    description: str | None
    business_context: str | None
    owner: str | None
    keywords: list[str]
    status: str
    source: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("service_metadata", "metadata"),
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class ServiceDependencyCreate(BaseModel):
    project_id: uuid.UUID
    from_service_id: uuid.UUID
    to_service_id: uuid.UUID
    dependency_type: str = "api_call"
    description: str | None = None
    confidence: int = 100


class ServiceDependencyResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    from_service_id: uuid.UUID
    to_service_id: uuid.UUID
    dependency_type: str
    description: str | None
    confidence: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ServiceConnectionBindingCreate(BaseModel):
    project_id: uuid.UUID
    service_id: uuid.UUID
    connection_id: uuid.UUID
    usage_type: str = "runtime_inspect"
    priority: int = 100
    notes: str | None = None


class ServiceConnectionBindingResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    service_id: uuid.UUID
    connection_id: uuid.UUID
    usage_type: str
    priority: int
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectTopologyResponse(BaseModel):
    project: ProjectResponse
    services: list[ServiceResponse]
    dependencies: list[ServiceDependencyResponse]
    connections: list[ConnectionResponse]
    bindings: list[ServiceConnectionBindingResponse]


class DiscoverServicesResponse(BaseModel):
    discovered: int
    services: list[ServiceResponse]


class MonitoringSourceCreate(BaseModel):
    project_id: uuid.UUID
    name: str
    source_type: Literal["prometheus", "loki"]
    endpoint: str
    auth_header: str | None = None


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


class IncidentCreate(BaseModel):
    title: str = ""
    description: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    project_id: uuid.UUID | None = None
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


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
    connection_id: uuid.UUID | None
    project_id: uuid.UUID | None
    summary_md: str | None
    thread_id: str | None
    saved_to_memory: bool
    attachments: list[AttachmentResponse] = Field(default_factory=list)
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
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


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
    decision: Literal["approved", "rejected"]
    decided_by: str = "admin"


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


class DocumentDetailResponse(DocumentResponse):
    content: str


class DocumentUpdate(BaseModel):
    content: str
