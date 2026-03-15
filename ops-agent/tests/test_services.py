"""Tests for infrastructure, incident, and approval services.

These are unit tests using in-memory mocks instead of a real database.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.infrastructure_service import InfrastructureService
from src.services.incident_service import IncidentService
from src.services.approval_service import ApprovalService


# ── Infrastructure Service ──


class TestInfrastructureService:
    @pytest.fixture
    def service(self):
        session = AsyncMock()
        session.add = MagicMock()  # add() is synchronous on AsyncSession
        crypto = MagicMock()
        crypto.encrypt.side_effect = lambda x: f"enc:{x}"
        crypto.decrypt.side_effect = lambda x: x.replace("enc:", "")
        return InfrastructureService(session=session, crypto=crypto)

    async def test_create_encrypts_password(self, service: InfrastructureService):
        result = await service.create(
            name="Web Server",
            host="192.168.1.10",
            port=22,
            username="root",
            password="secret123",
        )

        assert result.name == "Web Server"
        assert result.host == "192.168.1.10"
        assert result.encrypted_password == "enc:secret123"
        service.session.add.assert_called_once()
        service.session.commit.assert_called_once()

    async def test_create_encrypts_private_key(self, service: InfrastructureService):
        result = await service.create(
            name="Web Server",
            host="192.168.1.10",
            private_key="ssh-rsa AAAA...",
        )

        assert result.encrypted_private_key == "enc:ssh-rsa AAAA..."
        assert result.encrypted_password is None

    async def test_get_decrypted_credentials(self, service: InfrastructureService):
        infra = MagicMock()
        infra.encrypted_password = "enc:mypassword"
        infra.encrypted_private_key = None

        password, key = service.get_decrypted_credentials(infra)

        assert password == "mypassword"
        assert key is None


# ── Incident Service ──


class TestIncidentService:
    @pytest.fixture
    def service(self):
        session = AsyncMock()
        session.add = MagicMock()
        return IncidentService(session=session)

    async def test_create_incident(self, service: IncidentService):
        result = await service.create(
            title="Disk full",
            description="Server /dev/sda1 is 95% full",
            severity="high",
        )

        assert result.title == "Disk full"
        assert result.status == "open"
        assert result.severity == "high"
        service.session.add.assert_called_once()
        service.session.commit.assert_called_once()

    async def test_create_incident_with_infrastructure(self, service: IncidentService):
        infra_id = uuid.uuid4()
        result = await service.create(
            title="High CPU",
            description="CPU usage > 90%",
            infrastructure_id=infra_id,
        )

        assert result.infrastructure_id == infra_id

    async def test_update_status(self, service: IncidentService):
        incident = MagicMock()
        incident.status = "open"

        await service.update_status(incident, "investigating")

        assert incident.status == "investigating"
        service.session.commit.assert_called_once()

    async def test_save_message(self, service: IncidentService):
        incident_id = uuid.uuid4()

        await service.save_message(
            incident_id=incident_id,
            role="assistant",
            event_type="thinking",
            content="Analyzing disk usage...",
        )

        service.session.add.assert_called_once()
        service.session.commit.assert_called_once()


# ── Approval Service ──


class TestApprovalService:
    @pytest.fixture
    def service(self):
        session = AsyncMock()
        session.add = MagicMock()
        return ApprovalService(session=session)

    async def test_create_approval_request(self, service: ApprovalService):
        incident_id = uuid.uuid4()

        result = await service.create(
            incident_id=incident_id,
            tool_name="exec_write",
            tool_args='{"command": "rm /tmp/old_logs/*"}',
        )

        assert result.incident_id == incident_id
        assert result.tool_name == "exec_write"
        assert result.decision is None
        service.session.add.assert_called_once()

    async def test_approve(self, service: ApprovalService):
        approval = MagicMock()
        approval.decision = None

        result = await service.decide(approval, decision="approved", decided_by="admin")

        assert approval.decision == "approved"
        assert approval.decided_by == "admin"
        service.session.commit.assert_called_once()

    async def test_reject(self, service: ApprovalService):
        approval = MagicMock()
        approval.decision = None

        result = await service.decide(approval, decision="rejected", decided_by="admin")

        assert approval.decision == "rejected"

    async def test_duplicate_decision_raises(self, service: ApprovalService):
        approval = MagicMock()
        approval.decision = "approved"

        with pytest.raises(ValueError, match="already decided"):
            await service.decide(approval, decision="rejected", decided_by="admin")
