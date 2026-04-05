"""Tests for /api/versions endpoints."""

import uuid

from tests.factories import make_project_payload


class TestListVersions:
    async def test_list_versions_empty(self, client):
        resp = await client.get(
            "/api/versions",
            params={"entity_type": "skill", "entity_id": "nonexistent"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_versions_after_skill_create_and_update(self, client):
        # Create a skill (saves initial version)
        slug = f"test-skill-{uuid.uuid4().hex[:6]}"
        await client.post("/api/skills", json={"slug": slug})

        # Update it (saves another version)
        await client.put(f"/api/skills/{slug}", json={"content": "# Updated"})

        resp = await client.get(
            "/api/versions",
            params={"entity_type": "skill", "entity_id": slug},
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) >= 1
        assert versions[0]["entity_type"] == "skill"
        assert versions[0]["entity_id"] == slug


class TestGetVersion:
    async def test_get_version(self, client):
        # Create a skill to generate a version
        slug = f"test-skill-{uuid.uuid4().hex[:6]}"
        await client.post("/api/skills", json={"slug": slug})

        # Get version list
        list_resp = await client.get(
            "/api/versions",
            params={"entity_type": "skill", "entity_id": slug},
        )
        versions = list_resp.json()
        assert len(versions) >= 1

        version_id = versions[0]["id"]
        resp = await client.get(f"/api/versions/{version_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert data["id"] == version_id

    async def test_get_version_not_found(self, client):
        resp = await client.get(f"/api/versions/{uuid.uuid4()}")
        assert resp.status_code == 404
