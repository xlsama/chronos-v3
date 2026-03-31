"""Tests for /api/projects endpoints."""

import uuid

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


class TestListProjects:
    async def test_list_projects_empty(self, client):
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_projects(self, client):
        for _ in range(3):
            await client.post("/api/projects", json=make_project_payload())

        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

    async def test_list_projects_pagination(self, client):
        for _ in range(3):
            await client.post("/api/projects", json=make_project_payload())

        resp = await client.get("/api/projects", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3


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
