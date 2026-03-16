"""API endpoint tests for MonitoringSource routes."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.connections import get_crypto as conn_get_crypto
from src.api.monitoring_sources import get_crypto as ms_get_crypto
from src.db.connection import get_session
from src.main import app
from src.services.crypto import CryptoService

TEST_KEY = "dGVzdC1lbmNyeXB0aW9uLWtleS0zMmJ5dGVzMA=="


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    return session


def _mock_settings():
    m = MagicMock()
    m.encryption_key = TEST_KEY
    return m


@pytest.fixture
async def client(mock_session):
    async def override_session():
        yield mock_session

    test_crypto = CryptoService(key=TEST_KEY)
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[ms_get_crypto] = lambda: test_crypto
    app.dependency_overrides[conn_get_crypto] = lambda: test_crypto
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("src.api.monitoring_sources.get_settings", return_value=_mock_settings()):
            yield ac
    app.dependency_overrides.clear()


def _mock_source(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "name": "Prod Prometheus",
        "source_type": "prometheus",
        "endpoint": "http://prometheus:9090",
        "conn_config": None,
        "status": "unknown",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


async def test_create_monitoring_source(client: AsyncClient, mock_session):
    project_id = uuid.uuid4()
    mock_src = _mock_source(project_id=project_id)

    with patch("src.api.monitoring_sources.MonitoringSourceService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.create.return_value = mock_src
        mock_svc_cls.return_value = mock_svc

        response = await client.post("/api/monitoring-sources", json={
            "project_id": str(project_id),
            "name": "Prod Prometheus",
            "source_type": "prometheus",
            "endpoint": "http://prometheus:9090",
        })

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Prod Prometheus"
    assert data["source_type"] == "prometheus"


async def test_list_monitoring_sources(client: AsyncClient, mock_session):
    project_id = uuid.uuid4()
    mock_src = _mock_source(project_id=project_id)

    with patch("src.api.monitoring_sources.MonitoringSourceService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.list_by_project.return_value = [mock_src]
        mock_svc_cls.return_value = mock_svc

        response = await client.get(f"/api/monitoring-sources/by-project/{project_id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


async def test_delete_monitoring_source(client: AsyncClient, mock_session):
    source_id = uuid.uuid4()

    with patch("src.api.monitoring_sources.MonitoringSourceService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.delete.return_value = True
        mock_svc_cls.return_value = mock_svc

        response = await client.delete(f"/api/monitoring-sources/{source_id}")

    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_delete_monitoring_source_not_found(client: AsyncClient, mock_session):
    source_id = uuid.uuid4()

    with patch("src.api.monitoring_sources.MonitoringSourceService") as mock_svc_cls:
        mock_svc = AsyncMock()
        mock_svc.delete.return_value = False
        mock_svc_cls.return_value = mock_svc

        response = await client.delete(f"/api/monitoring-sources/{source_id}")

    assert response.status_code == 404


async def test_test_monitoring_source_prometheus(client: AsyncClient, mock_session):
    source_id = uuid.uuid4()
    mock_src = _mock_source(id=source_id, source_type="prometheus")

    with (
        patch("src.api.monitoring_sources.MonitoringSourceService") as mock_svc_cls,
        patch("src.api.monitoring_sources.PrometheusConnector") as mock_prom_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.get.return_value = mock_src
        mock_svc_cls.return_value = mock_svc

        mock_connector = AsyncMock()
        mock_connector.test_connection.return_value = True
        mock_prom_cls.return_value = mock_connector

        response = await client.post(f"/api/monitoring-sources/{source_id}/test")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Connection successful"


async def test_test_monitoring_source_loki(client: AsyncClient, mock_session):
    source_id = uuid.uuid4()
    mock_src = _mock_source(id=source_id, source_type="loki", endpoint="http://loki:3100")

    with (
        patch("src.api.monitoring_sources.MonitoringSourceService") as mock_svc_cls,
        patch("src.api.monitoring_sources.LokiConnector") as mock_loki_cls,
    ):
        mock_svc = AsyncMock()
        mock_svc.get.return_value = mock_src
        mock_svc_cls.return_value = mock_svc

        mock_connector = AsyncMock()
        mock_connector.test_connection.return_value = False
        mock_loki_cls.return_value = mock_connector

        response = await client.post(f"/api/monitoring-sources/{source_id}/test")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["message"] == "Connection failed"
