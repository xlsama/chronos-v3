"""API endpoint tests using FastAPI dependency overrides."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.infrastructures import get_crypto
from src.db.connection import get_session
from src.main import app
from src.services.crypto import CryptoService


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
async def client(mock_session):
    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_crypto] = lambda: CryptoService(
        key="dGVzdC1lbmNyeXB0aW9uLWtleS0zMmJ5dGVzMA=="
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Health ──


async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── Infrastructures ──


async def test_create_infrastructure(client: AsyncClient, mock_session):
    mock_infra = MagicMock()
    mock_infra.id = uuid.uuid4()
    mock_infra.name = "Web Server"
    mock_infra.type = "ssh"
    mock_infra.host = "192.168.1.10"
    mock_infra.port = 22
    mock_infra.username = "root"
    mock_infra.status = "unknown"
    mock_infra.project_id = None
    mock_infra.created_at = datetime.now(timezone.utc)
    mock_infra.updated_at = datetime.now(timezone.utc)

    with patch("src.api.infrastructures.InfrastructureService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.create.return_value = mock_infra
        mock_svc_cls.return_value = mock_svc

        response = await client.post("/api/infrastructures", json={
            "name": "Web Server",
            "host": "192.168.1.10",
            "password": "secret123",
        })

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Web Server"
    assert "password" not in data
    assert "encrypted_password" not in data


# ── Incidents ──


async def test_create_incident(client: AsyncClient, mock_session):
    mock_incident = MagicMock()
    mock_incident.id = uuid.uuid4()
    mock_incident.title = "Disk full"
    mock_incident.description = "Disk is 95% full"
    mock_incident.status = "open"
    mock_incident.severity = "high"
    mock_incident.infrastructure_id = None
    mock_incident.project_id = None
    mock_incident.summary_md = None
    mock_incident.thread_id = None
    mock_incident.saved_to_memory = False
    mock_incident.created_at = datetime.now(timezone.utc)
    mock_incident.updated_at = datetime.now(timezone.utc)

    # Mock agent_runner on app.state
    app.state.agent_runner = AsyncMock()

    with patch("src.api.incidents.IncidentService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.create.return_value = mock_incident
        mock_svc_cls.return_value = mock_svc

        response = await client.post("/api/incidents", json={
            "title": "Disk full",
            "description": "Disk is 95% full",
            "severity": "high",
        })

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Disk full"
    assert data["status"] == "open"


async def test_list_incidents(client: AsyncClient, mock_session):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    response = await client.get("/api/incidents")
    assert response.status_code == 200
    assert response.json() == []


# ── Approvals ──


async def test_decide_approval(client: AsyncClient, mock_session):
    approval_id = uuid.uuid4()
    incident_id = uuid.uuid4()

    # Before decide - first get returns approval, second get returns incident
    pre_approval = MagicMock()
    pre_approval.id = approval_id
    pre_approval.incident_id = incident_id
    pre_approval.decision = None

    mock_incident = MagicMock()
    mock_incident.id = incident_id
    mock_incident.thread_id = "thread-123"

    # After decide
    decided_approval = MagicMock()
    decided_approval.id = approval_id
    decided_approval.incident_id = incident_id
    decided_approval.tool_name = "exec_write"
    decided_approval.tool_args = '{"command": "systemctl restart nginx"}'
    decided_approval.decision = "approved"
    decided_approval.decided_by = "admin"
    decided_approval.decided_at = datetime.now(timezone.utc)
    decided_approval.risk_level = "MEDIUM"
    decided_approval.risk_detail = "短暂服务中断"
    decided_approval.explanation = "重启 nginx"
    decided_approval.created_at = datetime.now(timezone.utc)

    # mock_session.get is called twice: once for ApprovalRequest, once for Incident
    mock_session.get.side_effect = [pre_approval, mock_incident]

    # Mock agent_runner on app.state
    app.state.agent_runner = AsyncMock()

    with patch("src.api.approvals.ApprovalService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.decide.return_value = decided_approval
        mock_svc_cls.return_value = mock_svc

        response = await client.post(f"/api/approvals/{approval_id}/decide", json={
            "decision": "approved",
            "decided_by": "admin",
        })

    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "approved"


async def test_decide_approval_invalid_decision(client: AsyncClient, mock_session):
    approval_id = uuid.uuid4()
    mock_approval = MagicMock()
    mock_approval.decision = None
    mock_session.get.return_value = mock_approval

    response = await client.post(f"/api/approvals/{approval_id}/decide", json={
        "decision": "invalid",
    })

    assert response.status_code == 422


async def test_get_approval_not_found(client: AsyncClient, mock_session):
    mock_session.get.return_value = None

    response = await client.get(f"/api/approvals/{uuid.uuid4()}")
    assert response.status_code == 404


# ── Save to Memory ──


async def test_save_to_memory_endpoint(client: AsyncClient, mock_session):
    incident_id = uuid.uuid4()
    mock_incident = MagicMock()
    mock_incident.id = incident_id
    mock_incident.title = "Disk full"
    mock_incident.summary_md = "## Report\n\nDisk was full"
    mock_incident.saved_to_memory = False
    mock_incident.project_id = None

    mock_session.get.return_value = mock_incident

    mock_record = MagicMock()
    mock_record.id = uuid.uuid4()

    with patch("src.api.incidents.IncidentHistoryService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.save.return_value = mock_record
        mock_svc_cls.return_value = mock_svc

        response = await client.post(f"/api/incidents/{incident_id}/save-to-memory")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "incident_history_id" in data


async def test_save_to_memory_already_saved(client: AsyncClient, mock_session):
    incident_id = uuid.uuid4()
    mock_incident = MagicMock()
    mock_incident.id = incident_id
    mock_incident.saved_to_memory = True

    mock_session.get.return_value = mock_incident

    response = await client.post(f"/api/incidents/{incident_id}/save-to-memory")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "already_saved"
