"""API tests for document endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.documents import get_embedder
from src.db.connection import get_session
from src.main import app


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_embedder():
    return AsyncMock()


@pytest.fixture
async def client(mock_session, mock_embedder):
    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_embedder] = lambda: mock_embedder
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _mock_document(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "filename": "readme.md",
        "content": "# Hello",
        "doc_type": "markdown",
        "status": "ready",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _mock_project():
    m = MagicMock()
    m.id = uuid.uuid4()
    return m


async def test_upload_document(client: AsyncClient):
    project_id = uuid.uuid4()
    mock_doc = _mock_document(project_id=project_id)

    with (
        patch("src.api.documents.ProjectService") as mock_proj_cls,
        patch("src.api.documents.DocumentService") as mock_doc_cls,
    ):
        mock_proj_svc = AsyncMock()
        mock_proj_svc.get.return_value = _mock_project()
        mock_proj_cls.return_value = mock_proj_svc

        mock_doc_svc = AsyncMock()
        mock_doc_svc.upload.return_value = mock_doc
        mock_doc_cls.return_value = mock_doc_svc

        response = await client.post(f"/api/projects/{project_id}/documents", json={
            "filename": "readme.md",
            "content": "# Hello",
            "doc_type": "markdown",
        })

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "readme.md"
    assert data["status"] == "ready"


async def test_upload_document_project_not_found(client: AsyncClient):
    with patch("src.api.documents.ProjectService") as mock_proj_cls:
        mock_proj_svc = AsyncMock()
        mock_proj_svc.get.return_value = None
        mock_proj_cls.return_value = mock_proj_svc

        response = await client.post(f"/api/projects/{uuid.uuid4()}/documents", json={
            "filename": "readme.md",
            "content": "# Hello",
        })

    assert response.status_code == 404


async def test_list_documents(client: AsyncClient):
    project_id = uuid.uuid4()

    with patch("src.api.documents.DocumentService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.list_by_project.return_value = []
        mock_cls.return_value = mock_svc

        response = await client.get(f"/api/projects/{project_id}/documents")

    assert response.status_code == 200
    assert response.json() == []


async def test_delete_document(client: AsyncClient):
    doc_id = uuid.uuid4()

    with patch("src.api.documents.DocumentService") as mock_cls:
        mock_svc = AsyncMock()
        mock_cls.return_value = mock_svc

        response = await client.delete(f"/api/documents/{doc_id}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_delete_document_not_found(client: AsyncClient):
    doc_id = uuid.uuid4()

    with patch("src.api.documents.DocumentService") as mock_cls:
        mock_svc = AsyncMock()
        mock_svc.delete.side_effect = ValueError("Document not found")
        mock_cls.return_value = mock_svc

        response = await client.delete(f"/api/documents/{doc_id}")

    assert response.status_code == 404
