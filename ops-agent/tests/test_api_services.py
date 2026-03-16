"""API endpoint tests for Services routes."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.db.connection import get_session
from src.main import app


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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _mock_service(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "infrastructure_id": uuid.uuid4(),
        "name": "nginx",
        "service_type": "docker_container",
        "port": 80,
        "namespace": None,
        "config_json": None,
        "status": "unknown",
        "discovery_method": "manual",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


async def test_create_service(client: AsyncClient, mock_session):
    infra_id = uuid.uuid4()
    mock_svc = _mock_service(infrastructure_id=infra_id)

    with patch("src.api.services.ServiceCatalog") as mock_catalog_cls:
        mock_catalog = AsyncMock()
        mock_catalog.create.return_value = mock_svc
        mock_catalog_cls.return_value = mock_catalog

        response = await client.post("/api/services", json={
            "infrastructure_id": str(infra_id),
            "name": "nginx",
            "service_type": "docker_container",
            "port": 80,
        })

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "nginx"
    assert data["service_type"] == "docker_container"


async def test_list_services_by_infra(client: AsyncClient, mock_session):
    infra_id = uuid.uuid4()
    mock_svc = _mock_service(infrastructure_id=infra_id)

    with patch("src.api.services.ServiceCatalog") as mock_catalog_cls:
        mock_catalog = AsyncMock()
        mock_catalog.list_by_infra.return_value = [mock_svc]
        mock_catalog_cls.return_value = mock_catalog

        response = await client.get(f"/api/services/by-infra/{infra_id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "nginx"


async def test_get_service(client: AsyncClient, mock_session):
    svc_id = uuid.uuid4()
    mock_svc = _mock_service(id=svc_id)

    with patch("src.api.services.ServiceCatalog") as mock_catalog_cls:
        mock_catalog = AsyncMock()
        mock_catalog.get.return_value = mock_svc
        mock_catalog_cls.return_value = mock_catalog

        response = await client.get(f"/api/services/{svc_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "nginx"


async def test_delete_service(client: AsyncClient, mock_session):
    svc_id = uuid.uuid4()

    with patch("src.api.services.ServiceCatalog") as mock_catalog_cls:
        mock_catalog = AsyncMock()
        mock_catalog.delete.return_value = True
        mock_catalog_cls.return_value = mock_catalog

        response = await client.delete(f"/api/services/{svc_id}")

    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_delete_service_not_found(client: AsyncClient, mock_session):
    svc_id = uuid.uuid4()

    with patch("src.api.services.ServiceCatalog") as mock_catalog_cls:
        mock_catalog = AsyncMock()
        mock_catalog.delete.return_value = False
        mock_catalog_cls.return_value = mock_catalog

        response = await client.delete(f"/api/services/{svc_id}")

    assert response.status_code == 404


async def test_discover_services(client: AsyncClient, mock_session):
    infra_id = uuid.uuid4()
    mock_svc = _mock_service(infrastructure_id=infra_id, discovery_method="auto_discovered")

    with patch("src.api.services.ServiceCatalog") as mock_catalog_cls:
        mock_catalog = AsyncMock()
        mock_catalog.auto_discover.return_value = [mock_svc]
        mock_catalog_cls.return_value = mock_catalog

        response = await client.post(f"/api/services/discover/{infra_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["discovered"] == 1
    assert len(data["services"]) == 1
