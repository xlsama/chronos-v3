"""API tests for project endpoints."""

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


def _mock_project(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Project",
        "slug": "test-project",
        "description": "A test project",
        "cloud_md": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


async def test_create_project(client: AsyncClient):
    mock_proj = _mock_project()

    with patch("src.api.projects.ProjectService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.create.return_value = mock_proj
        mock_cls.return_value = mock_svc

        response = await client.post("/api/projects", json={
            "name": "Test Project",
            "description": "A test project",
        })

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Project"
    assert data["slug"] == "test-project"


async def test_list_projects(client: AsyncClient):
    with patch("src.api.projects.ProjectService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.list.return_value = []
        mock_cls.return_value = mock_svc

        response = await client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_project(client: AsyncClient):
    mock_proj = _mock_project()

    with patch("src.api.projects.ProjectService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.get.return_value = mock_proj
        mock_cls.return_value = mock_svc

        response = await client.get(f"/api/projects/{mock_proj.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Test Project"


async def test_get_project_not_found(client: AsyncClient):
    with patch("src.api.projects.ProjectService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.get.return_value = None
        mock_cls.return_value = mock_svc

        response = await client.get(f"/api/projects/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_update_project(client: AsyncClient):
    mock_proj = _mock_project(name="Updated")

    with patch("src.api.projects.ProjectService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.get.return_value = mock_proj
        mock_svc.update.return_value = mock_proj
        mock_cls.return_value = mock_svc

        response = await client.patch(f"/api/projects/{mock_proj.id}", json={
            "name": "Updated",
        })

    assert response.status_code == 200
    assert response.json()["name"] == "Updated"


async def test_update_cloud_md(client: AsyncClient):
    mock_proj = _mock_project(cloud_md="# Updated Cloud MD")

    with patch("src.api.projects.ProjectService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.get.return_value = mock_proj
        mock_svc.update_cloud_md.return_value = mock_proj
        mock_cls.return_value = mock_svc

        response = await client.patch(f"/api/projects/{mock_proj.id}/cloud-md", json={
            "cloud_md": "# Updated Cloud MD",
        })

    assert response.status_code == 200
    assert response.json()["cloud_md"] == "# Updated Cloud MD"


async def test_delete_project(client: AsyncClient):
    mock_proj = _mock_project()

    with patch("src.api.projects.ProjectService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.get.return_value = mock_proj
        mock_cls.return_value = mock_svc

        response = await client.delete(f"/api/projects/{mock_proj.id}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_delete_project_not_found(client: AsyncClient):
    with patch("src.api.projects.ProjectService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.get.return_value = None
        mock_cls.return_value = mock_svc

        response = await client.delete(f"/api/projects/{uuid.uuid4()}")

    assert response.status_code == 404
