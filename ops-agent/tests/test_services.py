"""Tests for infrastructure, incident, approval, and incident history services.

These are unit tests using in-memory mocks instead of a real database.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.infrastructure_service import InfrastructureService
from src.services.incident_service import IncidentService
from src.services.approval_service import ApprovalService
from src.services.incident_history_service import IncidentHistoryService


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

    async def test_create_k8s_encrypts_kubeconfig(self, service: InfrastructureService):
        result = await service.create(
            name="K8s Cluster",
            type="kubernetes",
            kubeconfig="apiVersion: v1\nclusters: []",
            context="my-context",
            namespace="production",
        )

        assert result.name == "K8s Cluster"
        assert result.type == "kubernetes"
        assert result.conn_config is not None
        assert result.conn_config.startswith("enc:")
        service.crypto.encrypt.assert_called()
        service.session.add.assert_called_once()

    async def test_create_k8s_without_kubeconfig(self, service: InfrastructureService):
        result = await service.create(
            name="K8s Cluster",
            type="kubernetes",
        )

        assert result.conn_config is None

    async def test_get_decrypted_conn_config(self, service: InfrastructureService):
        import orjson

        config_data = {"kubeconfig": "apiVersion: v1\nclusters: []", "context": "my-ctx"}
        encrypted = f"enc:{orjson.dumps(config_data).decode()}"

        infra = MagicMock()
        infra.conn_config = encrypted

        result = service.get_decrypted_conn_config(infra)

        assert result is not None
        assert result["kubeconfig"] == "apiVersion: v1\nclusters: []"
        assert result["context"] == "my-ctx"

    async def test_get_decrypted_conn_config_none(self, service: InfrastructureService):
        infra = MagicMock()
        infra.conn_config = None

        result = service.get_decrypted_conn_config(infra)

        assert result is None


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

    async def test_create_approval_request_with_risk_fields(self, service: ApprovalService):
        incident_id = uuid.uuid4()

        result = await service.create(
            incident_id=incident_id,
            tool_name="exec_write_tool",
            tool_args='{"command": "systemctl restart nginx"}',
            risk_level="MEDIUM",
            risk_detail="短暂服务中断",
            explanation="重启 nginx 恢复服务",
        )

        assert result.incident_id == incident_id
        assert result.risk_level == "MEDIUM"
        assert result.risk_detail == "短暂服务中断"
        assert result.explanation == "重启 nginx 恢复服务"
        service.session.add.assert_called()

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


# ── IncidentHistory Service ──


class TestIncidentHistoryService:
    @pytest.fixture
    def mock_embedder(self):
        embedder = AsyncMock()
        embedder.embed_text.return_value = [0.1] * 1024
        return embedder

    @pytest.fixture
    def service(self, mock_embedder):
        session = AsyncMock()
        session.add = MagicMock()
        return IncidentHistoryService(session=session, embedder=mock_embedder)

    async def test_save_creates_record_with_embedding(self, service, mock_embedder, tmp_path):
        incident_id = uuid.uuid4()
        mock_incident = MagicMock()
        mock_incident.saved_to_memory = False
        service.session.get.return_value = mock_incident

        # Patch HISTORY_DIR to tmp_path
        with patch("src.services.incident_history_service.HISTORY_DIR", tmp_path):
            result = await service.save(
                incident_id=incident_id,
                project_id=None,
                title="Disk Full Alert",
                summary_md="# Disk full\n\nDisk was 95% full.",
            )

        assert result.title == "Disk Full Alert"
        assert result.summary_md == "# Disk full\n\nDisk was 95% full."
        assert result.embedding == [0.1] * 1024
        mock_embedder.embed_text.assert_called_once_with("# Disk full\n\nDisk was 95% full.")
        service.session.add.assert_called_once()
        service.session.commit.assert_called_once()

    async def test_save_writes_markdown_file(self, service, tmp_path):
        incident_id = uuid.uuid4()
        service.session.get.return_value = MagicMock(saved_to_memory=False)

        with patch("src.services.incident_history_service.HISTORY_DIR", tmp_path):
            result = await service.save(
                incident_id=incident_id,
                project_id=None,
                title="OOM Kill",
                summary_md="# OOM\n\nProcess killed.",
            )

        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 1
        assert "OOM" in md_files[0].read_text()

    async def test_save_updates_saved_to_memory(self, service, tmp_path):
        incident_id = uuid.uuid4()
        mock_incident = MagicMock()
        mock_incident.saved_to_memory = False
        service.session.get.return_value = mock_incident

        with patch("src.services.incident_history_service.HISTORY_DIR", tmp_path):
            await service.save(
                incident_id=incident_id,
                project_id=None,
                title="Test",
                summary_md="Test summary",
            )

        assert mock_incident.saved_to_memory is True

    async def test_search_returns_formatted_results(self, service, mock_embedder):
        mock_row = MagicMock()
        mock_row.title = "Disk Full"
        mock_row.summary_md = "Disk was full"
        mock_row.distance = 0.15

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        service.session.execute.return_value = mock_result

        results = await service.search(query="disk full", project_id=None)

        assert len(results) == 1
        assert results[0]["title"] == "Disk Full"
        assert results[0]["distance"] == 0.15
        mock_embedder.embed_text.assert_called_with("disk full")
