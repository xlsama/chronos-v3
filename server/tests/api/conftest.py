"""API test fixtures and helpers."""

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ApprovalRequest, Incident, IncidentHistory, Message
from tests.factories import make_register_payload


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Register a test user and return auth headers."""
    payload = make_register_payload()
    await client.post("/api/auth/register", json=payload)
    resp = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_incident_in_db(
    session: AsyncSession,
    *,
    description: str = "test incident",
    status: str = "open",
    severity: str = "P3",
    thread_id: str | None = None,
) -> Incident:
    """Insert an Incident directly into the DB (bypass API)."""
    incident = Incident(
        description=description,
        status=status,
        severity=severity,
        thread_id=thread_id,
    )
    session.add(incident)
    await session.flush()
    await session.refresh(incident)
    return incident


async def create_approval_in_db(
    session: AsyncSession,
    incident_id: uuid.UUID,
    *,
    tool_name: str = "ssh_bash",
    tool_args: str = '{"command": "ls"}',
    risk_level: str = "HIGH",
) -> ApprovalRequest:
    """Insert an ApprovalRequest directly into the DB."""
    approval = ApprovalRequest(
        incident_id=incident_id,
        tool_name=tool_name,
        tool_args=tool_args,
        risk_level=risk_level,
    )
    session.add(approval)
    await session.flush()
    await session.refresh(approval)
    return approval


async def create_message_in_db(
    session: AsyncSession,
    incident_id: uuid.UUID,
    *,
    role: str = "assistant",
    event_type: str = "thinking",
    content: str = "test content",
    metadata_json: dict | None = None,
) -> Message:
    """Insert a Message directly into the DB."""
    message = Message(
        incident_id=incident_id,
        role=role,
        event_type=event_type,
        content=content,
        metadata_json=metadata_json,
    )
    session.add(message)
    await session.flush()
    await session.refresh(message)
    return message


async def create_incident_history_in_db(
    session: AsyncSession,
    *,
    title: str = "Test history",
    summary_md: str = "## Summary\n\nTest incident history.",
) -> IncidentHistory:
    """Insert an IncidentHistory directly into the DB."""
    record = IncidentHistory(
        title=title,
        summary_md=summary_md,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record
