"""Tests for /api/projects endpoints."""

import uuid

from src.lib.paths import knowledge_dir
from tests.factories import make_project_payload


class TestCreateProject:
    async def test_create_project(self, client):
        payload = make_project_payload()
        resp = await client.post("/api/projects", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["slug"] == payload["slug"]
        assert "id" in data

    async def test_create_project_auto_slug(self, client):
        payload = {"name": "My Cool Project"}
        resp = await client.post("/api/projects", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Cool Project"
        assert data["slug"]  # auto-generated, non-empty

    async def test_create_project_with_description(self, client):
        payload = make_project_payload(description="A test project")
        resp = await client.post("/api/projects", json=payload)
        assert resp.status_code == 200
        assert resp.json()["description"] == "A test project"

    async def test_create_project_auto_creates_memory_md(self, client):
        payload = make_project_payload()
        resp = await client.post("/api/projects", json=payload)
        assert resp.status_code == 200

        project_id = resp.json()["id"]
        docs_resp = await client.get(f"/api/projects/{project_id}/documents")
        assert docs_resp.status_code == 200

        memory_doc = next(doc for doc in docs_resp.json() if doc["doc_type"] == "memory_config")
        assert memory_doc["filename"] == "MEMORY.md"
        assert (knowledge_dir(payload["slug"]) / "MEMORY.md").exists()


class TestListProjects:
    async def test_list_projects_empty(self, client):
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["items"], list)
        assert data["total"] >= len(data["items"])

    async def test_list_projects(self, client):
        before_resp = await client.get("/api/projects")
        before_total = before_resp.json()["total"]

        for _ in range(3):
            await client.post("/api/projects", json=make_project_payload())

        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == before_total + 3

    async def test_list_projects_pagination(self, client):
        before_resp = await client.get("/api/projects")
        before_total = before_resp.json()["total"]

        for _ in range(3):
            await client.post("/api/projects", json=make_project_payload())

        resp = await client.get("/api/projects", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == before_total + 3


class TestGetProject:
    async def test_get_project(self, client):
        create_resp = await client.post("/api/projects", json=make_project_payload())
        project_id = create_resp.json()["id"]

        resp = await client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == project_id

    async def test_get_project_not_found(self, client):
        resp = await client.get(f"/api/projects/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateProject:
    async def test_update_project(self, client):
        create_resp = await client.post("/api/projects", json=make_project_payload())
        project_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/projects/{project_id}", json={"name": "Updated Name"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_project_partial(self, client):
        payload = make_project_payload()
        create_resp = await client.post("/api/projects", json=payload)
        project_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/projects/{project_id}", json={"description": "new desc"}
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "new desc"
        assert resp.json()["name"] == payload["name"]

    async def test_update_project_not_found(self, client):
        resp = await client.patch(
            f"/api/projects/{uuid.uuid4()}", json={"name": "x"}
        )
        assert resp.status_code == 404


class TestDeleteProject:
    async def test_delete_project(self, client):
        create_resp = await client.post("/api/projects", json=make_project_payload())
        project_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/projects/{project_id}")
        assert resp.status_code == 204

        get_resp = await client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 404

    async def test_delete_project_not_found(self, client):
        resp = await client.delete(f"/api/projects/{uuid.uuid4()}")
        assert resp.status_code == 404
