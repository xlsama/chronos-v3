import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ProjectCreate(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    linked_server_ids: list[uuid.UUID] | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    linked_server_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServerCreate(BaseModel):
    name: str
    description: str | None = None
    host: str
    port: int = 22
    username: str = "root"
    password: str | None = None
    private_key: str | None = None
    bastion_host: str | None = None
    bastion_port: int | None = None
    bastion_username: str | None = None
    bastion_password: str | None = None
    bastion_private_key: str | None = None


class ServerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    private_key: str | None = None
    bastion_host: str | None = None
    bastion_port: int | None = None
    bastion_username: str | None = None
    bastion_password: str | None = None
    bastion_private_key: str | None = None


class ServerResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    host: str
    port: int
    username: str
    status: str
    auth_method: str = "none"
    has_bastion: bool = False
    bastion_host: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def compute_derived_fields(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            if getattr(data, "encrypted_private_key", None):
                data.__dict__["auth_method"] = "private_key"
            elif getattr(data, "encrypted_password", None):
                data.__dict__["auth_method"] = "password"
            else:
                data.__dict__["auth_method"] = "none"
            data.__dict__["has_bastion"] = bool(getattr(data, "bastion_host", None))
        return data


class ServerTestResponse(BaseModel):
    success: bool
    message: str



class IncidentCreate(BaseModel):
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
    description: str
    status: str
    severity: str
    project_id: uuid.UUID | None
    summary_md: str | None
    summary_title: str | None
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
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    content: str


class EventResponse(BaseModel):
    event_type: str
    data: dict[str, Any]
    timestamp: str


class DocumentUpdate(BaseModel):
    content: str


class IncidentHistoryResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    summary_md: str
    occurrence_count: int
    last_seen_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentHistoryListResponse(BaseModel):
    items: list[IncidentHistoryResponse]
    total: int
    page: int
    page_size: int


class NotificationSettingsResponse(BaseModel):
    id: uuid.UUID
    platform: str
    webhook_url: str
    sign_key: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class NotificationSettingsUpsert(BaseModel):
    webhook_url: str
    sign_key: str | None = None
    enabled: bool = True


class WebhookTestRequest(BaseModel):
    webhook_url: str
    sign_key: str | None = None
    platform: Literal["feishu"] = "feishu"


class WebhookTestResponse(BaseModel):
    success: bool
    message: str


class SkillCreate(BaseModel):
    slug: str
    name: str
    description: str
    content: str


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None


class SkillResponse(BaseModel):
    slug: str
    name: str
    description: str
    created_at: str
    updated_at: str


class SkillDetailResponse(SkillResponse):
    content: str
