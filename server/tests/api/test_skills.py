"""Tests for /api/skills endpoints."""

import uuid


class TestCreateSkill:
    async def test_create_skill(self, client):
        resp = await client.post("/api/skills", json={"slug": f"test-skill-{uuid.uuid4().hex[:6]}"})
        assert resp.status_code == 201
        data = resp.json()
        assert "slug" in data
        assert "created_at" in data

    async def test_create_skill_duplicate(self, client):
        slug = f"test-skill-{uuid.uuid4().hex[:6]}"
        resp1 = await client.post("/api/skills", json={"slug": slug})
        assert resp1.status_code == 201

        resp2 = await client.post("/api/skills", json={"slug": slug})
        assert resp2.status_code == 409


class TestListSkills:
    async def test_list_skills(self, client):
        resp = await client.get("/api/skills")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestGetSkill:
    async def test_get_skill(self, client):
        slug = f"test-skill-{uuid.uuid4().hex[:6]}"
        await client.post("/api/skills", json={"slug": slug})

        resp = await client.get(f"/api/skills/{slug}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == slug
        assert "content" in data

    async def test_get_skill_not_found(self, client):
        resp = await client.get("/api/skills/nonexistent-skill-xyz")
        assert resp.status_code == 404


class TestUpdateSkill:
    async def test_update_skill(self, client):
        slug = f"test-skill-{uuid.uuid4().hex[:6]}"
        await client.post("/api/skills", json={"slug": slug})

        new_content = "---\nname: Updated Skill\n---\n\n# Updated content"
        resp = await client.put(f"/api/skills/{slug}", json={"content": new_content})
        assert resp.status_code == 200

        # Verify content updated
        get_resp = await client.get(f"/api/skills/{slug}")
        assert new_content in get_resp.json()["content"]

    async def test_update_skill_not_found(self, client):
        resp = await client.put(
            "/api/skills/nonexistent-skill-xyz",
            json={"content": "x"},
        )
        assert resp.status_code == 404


class TestDeleteSkill:
    async def test_delete_skill(self, client):
        slug = f"test-skill-{uuid.uuid4().hex[:6]}"
        await client.post("/api/skills", json={"slug": slug})

        resp = await client.delete(f"/api/skills/{slug}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        get_resp = await client.get(f"/api/skills/{slug}")
        assert get_resp.status_code == 404

    async def test_delete_skill_not_found(self, client):
        resp = await client.delete("/api/skills/nonexistent-skill-xyz")
        assert resp.status_code == 404


class TestSkillFiles:
    async def _create_skill(self, client) -> str:
        slug = f"test-skill-{uuid.uuid4().hex[:6]}"
        await client.post("/api/skills", json={"slug": slug})
        return slug

    async def test_put_and_get_skill_file(self, client):
        slug = await self._create_skill(client)

        # Create a script file
        resp = await client.put(
            f"/api/skills/{slug}/files/scripts/check.sh",
            json={"content": "#!/bin/bash\necho hello"},
        )
        assert resp.status_code == 200

        # Read it back
        get_resp = await client.get(f"/api/skills/{slug}/files/scripts/check.sh")
        assert get_resp.status_code == 200
        assert "echo hello" in get_resp.json()["content"]

    async def test_get_skill_file_not_found(self, client):
        slug = await self._create_skill(client)
        resp = await client.get(f"/api/skills/{slug}/files/scripts/nope.sh")
        assert resp.status_code == 404

    async def test_delete_skill_file(self, client):
        slug = await self._create_skill(client)

        # Create then delete
        await client.put(
            f"/api/skills/{slug}/files/scripts/temp.sh",
            json={"content": "echo temp"},
        )
        resp = await client.delete(f"/api/skills/{slug}/files/scripts/temp.sh")
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/skills/{slug}/files/scripts/temp.sh")
        assert get_resp.status_code == 404
