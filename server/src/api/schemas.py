import uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


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


class ServiceCreate(BaseModel):
    name: str
    description: str | None = None
    service_type: Literal[
        "mysql", "postgresql", "redis", "prometheus",
        "mongodb", "elasticsearch",
        "doris", "starrocks", "jenkins", "kettle", "hive",
        "kubernetes",
    ]
    host: str
    port: int
    password: str | None = None
    config: dict = Field(default_factory=dict)


class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    service_type: str | None = None
    host: str | None = None
    port: int | None = None
    password: str | None = None
    config: dict | None = None


class ServiceResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    service_type: str
    host: str
    port: int
    config: dict
    has_password: bool
    status: str
    created_at: datetime
    updated_at: datetime



class IncidentCreate(BaseModel):
    description: str
    severity: Literal["P0", "P1", "P2", "P3"] = "P3"
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID | None
    filename: str
    stored_filename: str
    content_type: str
    size: int
    parsed_content: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentResponse(BaseModel):
    id: uuid.UUID
    description: str
    status: str
    severity: str
    summary_title: str | None
    thread_id: str | None
    saved_to_memory: bool
    is_archived: bool
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
    metadata_json: dict | None
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
    event_id: str | None = None
    event_type: str
    data: dict[str, Any]
    timestamp: str


class DocumentUpdate(BaseModel):
    content: str


class IncidentHistoryResponse(BaseModel):
    id: uuid.UUID
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


class ContentVersionResponse(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: str
    version_number: int
    change_source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ContentVersionDetailResponse(ContentVersionResponse):
    content: str


class SkillCreate(BaseModel):
    slug: str


class SkillUpdate(BaseModel):
    content: str


class SkillFileUpdate(BaseModel):
    content: str


class SkillResponse(BaseModel):
    slug: str
    name: str = ""
    description: str = ""
    has_scripts: bool = False
    has_references: bool = False
    has_assets: bool = False
    draft: bool = False
    created_at: str
    updated_at: str


class SkillDetailResponse(SkillResponse):
    content: str
    script_files: list[str] = Field(default_factory=list)
    reference_files: list[str] = Field(default_factory=list)
    asset_files: list[str] = Field(default_factory=list)
