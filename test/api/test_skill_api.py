"""Skill HTTP API 测试 — 通过 httpx.AsyncClient + ASGITransport 测试 FastAPI 端点"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

# 路径设置
SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"
os.chdir(SERVER_DIR)
sys.path.insert(0, str(SERVER_DIR))

pytestmark = pytest.mark.api

SKILL_CONTENT = "---\nname: Test Skill\ndescription: A test skill for API testing\n---\n\n# Test Skill\n\nSome body content.\n"


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    from src.main import app
    from src.services.skill_service import SkillService
    from src.db.connection import get_session

    svc = SkillService(base_dir=tmp_path)
    monkeypatch.setattr("src.api.skills._get_service", lambda: svc)

    # Mock get_session to bypass DB dependency (VersionService needs execute -> scalar)
    async def mock_session():
        mock = AsyncMock()
        mock.commit = AsyncMock()
        mock.flush = AsyncMock()
        mock.add = MagicMock()
        # execute returns a result whose scalar() is sync and returns 0
        exec_result = MagicMock()
        exec_result.scalar.return_value = 0
        mock.execute = AsyncMock(return_value=exec_result)
        yield mock

    app.dependency_overrides[get_session] = mock_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, svc

    app.dependency_overrides.clear()


# ===== List Skills =====

class TestListSkills:
    async def test_list_empty(self, client):
        ac, _ = client
        resp = await ac.get("/api/skills")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_skills(self, client):
        ac, svc = client
        svc.create_skill("skill-a")
        svc.update_skill("skill-a", SKILL_CONTENT)
        svc.create_skill("skill-b")
        svc.update_skill("skill-b", SKILL_CONTENT.replace("Test Skill", "Skill B"))
        resp = await ac.get("/api/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_list_response_schema(self, client):
        ac, svc = client
        svc.create_skill("schema-test")
        svc.update_skill("schema-test", SKILL_CONTENT)
        resp = await ac.get("/api/skills")
        item = resp.json()[0]
        expected_keys = {"slug", "name", "description", "has_scripts", "has_references", "has_assets", "draft", "created_at", "updated_at"}
        assert expected_keys == set(item.keys())


# ===== Get Skill =====

class TestGetSkill:
    async def test_get_existing_skill(self, client):
        ac, svc = client
        svc.create_skill("my-skill")
        svc.update_skill("my-skill", SKILL_CONTENT)
        resp = await ac.get("/api/skills/my-skill")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "my-skill"
        assert data["name"] == "Test Skill"

    async def test_get_nonexistent_404(self, client):
        ac, _ = client
        resp = await ac.get("/api/skills/no-exist")
        assert resp.status_code == 404

    async def test_get_includes_content_and_files(self, client):
        ac, svc = client
        svc.create_skill("detail-skill")
        svc.update_skill("detail-skill", SKILL_CONTENT)
        svc.write_skill_file("detail-skill", "scripts/check.sh", "#!/bin/bash\necho ok")
        svc.write_skill_file("detail-skill", "assets/tpl.md", "# template")
        resp = await ac.get("/api/skills/detail-skill")
        data = resp.json()
        assert "content" in data
        assert "---" in data["content"]
        assert data["script_files"] == ["check.sh"]
        assert data["asset_files"] == ["tpl.md"]
        assert data["has_scripts"] is True
        assert data["has_assets"] is True


# ===== Create Skill =====

class TestCreateSkill:
    async def test_create_success(self, client):
        ac, _ = client
        resp = await ac.post("/api/skills", json={"slug": "new-skill"})
        assert resp.status_code == 201
        assert resp.json()["slug"] == "new-skill"

    async def test_create_duplicate_409(self, client):
        ac, _ = client
        await ac.post("/api/skills", json={"slug": "dup-skill"})
        resp = await ac.post("/api/skills", json={"slug": "dup-skill"})
        assert resp.status_code == 409


# ===== Update Skill =====

class TestUpdateSkill:
    async def test_update_success(self, client):
        ac, svc = client
        svc.create_skill("upd-skill")
        svc.update_skill("upd-skill", SKILL_CONTENT)
        new_content = SKILL_CONTENT.replace("Test Skill", "Updated Skill")
        resp = await ac.put("/api/skills/upd-skill", json={"content": new_content})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Skill"

    async def test_update_nonexistent_404(self, client):
        ac, _ = client
        resp = await ac.put("/api/skills/no-exist", json={"content": "whatever"})
        assert resp.status_code == 404


# ===== Delete Skill =====

class TestDeleteSkill:
    async def test_delete_success(self, client):
        ac, svc = client
        svc.create_skill("del-skill")
        resp = await ac.delete("/api/skills/del-skill")
        assert resp.status_code == 200

    async def test_delete_nonexistent_404(self, client):
        ac, _ = client
        resp = await ac.delete("/api/skills/no-exist")
        assert resp.status_code == 404

    async def test_delete_removes_from_list(self, client):
        ac, svc = client
        svc.create_skill("gone-skill")
        await ac.delete("/api/skills/gone-skill")
        resp = await ac.get("/api/skills")
        slugs = [s["slug"] for s in resp.json()]
        assert "gone-skill" not in slugs


# ===== File Operations =====

class TestSkillFileOps:
    async def test_write_and_read_file(self, client):
        ac, svc = client
        svc.create_skill("file-skill")
        svc.update_skill("file-skill", SKILL_CONTENT)
        # Write
        resp = await ac.put("/api/skills/file-skill/files/scripts/check.sh", json={"content": "#!/bin/bash\necho ok"})
        assert resp.status_code == 200
        # Read
        resp = await ac.get("/api/skills/file-skill/files/scripts/check.sh")
        assert resp.status_code == 200
        assert resp.json()["content"] == "#!/bin/bash\necho ok"

    async def test_read_nonexistent_file_404(self, client):
        ac, svc = client
        svc.create_skill("file-skill2")
        resp = await ac.get("/api/skills/file-skill2/files/scripts/no.sh")
        assert resp.status_code == 404

    async def test_path_traversal_400(self, client):
        """路径中不在合法子目录下 -> 400"""
        ac, svc = client
        svc.create_skill("file-skill3")
        svc.update_skill("file-skill3", SKILL_CONTENT)
        # 非法子目录 -> 400
        resp = await ac.get("/api/skills/file-skill3/files/hacks/evil.sh")
        assert resp.status_code == 400

    async def test_delete_file(self, client):
        ac, svc = client
        svc.create_skill("file-skill4")
        svc.update_skill("file-skill4", SKILL_CONTENT)
        svc.write_skill_file("file-skill4", "scripts/del.sh", "content")
        resp = await ac.delete("/api/skills/file-skill4/files/scripts/del.sh")
        assert resp.status_code == 200
