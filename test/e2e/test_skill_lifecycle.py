"""Skill 系统 E2E 测试 — 完整生命周期"""

import os
import sys
from pathlib import Path

import pytest

# 路径设置
SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"
os.chdir(SERVER_DIR)
sys.path.insert(0, str(SERVER_DIR))

pytestmark = pytest.mark.e2e

SLUG = "test-e2e"
SKILL_CONTENT = """---
name: E2E 测试技能
description: 用于端到端测试的技能，检查完整生命周期
---

# E2E 测试技能

## 步骤一
执行检查命令。

## 步骤二
分析结果。
"""

SCRIPT_CONTENT = "#!/bin/bash\necho 'E2E test check'\nfree -m"
REFERENCE_CONTENT = "# 参考文档\n\n这是一份参考文档。"


@pytest.fixture(autouse=True)
def cleanup():
    """测试结束后清理 skill"""
    yield
    from src.services.skill_service import SkillService

    svc = SkillService()
    try:
        svc.delete_skill(SLUG)
    except FileNotFoundError:
        pass


class TestSkillLifecycle:
    """完整生命周期测试：创建 → 编辑 → 添加文件 → 查询 → Agent 集成 → 清理"""

    def test_01_create_skill(self):
        """1. 创建 skill"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        meta = svc.create_skill(SLUG)
        assert meta.slug == SLUG
        assert meta.name == SLUG  # default name is slug

    def test_02_update_skill_md(self):
        """2. 更新 SKILL.md"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        meta = svc.update_skill(SLUG, SKILL_CONTENT)
        assert meta.name == "E2E 测试技能"
        assert meta.description == "用于端到端测试的技能，检查完整生命周期"

    def test_03_add_script_file(self):
        """3. 添加 scripts/check.sh"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)
        svc.write_skill_file(SLUG, "scripts/check.sh", SCRIPT_CONTENT)
        files = svc.list_skill_files(SLUG)
        assert "check.sh" in files["scripts"]

    def test_04_add_reference_file(self):
        """4. 添加 references/guide.md"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)
        svc.write_skill_file(SLUG, "references/guide.md", REFERENCE_CONTENT)
        files = svc.list_skill_files(SLUG)
        assert "guide.md" in files["references"]

    def test_05_get_skill_has_files(self):
        """5. 获取 skill 详情验证 has_scripts"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)
        svc.write_skill_file(SLUG, "scripts/check.sh", SCRIPT_CONTENT)
        svc.write_skill_file(SLUG, "references/guide.md", REFERENCE_CONTENT)

        meta, raw = svc.get_skill(SLUG)
        assert meta.has_scripts is True
        assert meta.has_references is True
        assert "check.sh" in meta.script_files
        assert "guide.md" in meta.reference_files

    def test_06_available_skills_includes(self):
        """6. get_available_skills() 包含 test-e2e"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)

        available = svc.get_available_skills()
        slugs = [s["slug"] for s in available]
        assert SLUG in slugs

    def test_07_read_skill_returns_body_and_files(self):
        """7. read_file(slug) 返回 SKILL.md body + 文件列表"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)
        svc.write_skill_file(SLUG, "scripts/check.sh", SCRIPT_CONTENT)

        result = svc.read_file(SLUG)
        assert "E2E 测试技能" in result
        assert "步骤一" in result
        assert "check.sh" in result

    def test_08_read_skill_returns_script(self):
        """8. read_file(slug, rel_path) 返回脚本内容"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)
        svc.write_skill_file(SLUG, "scripts/check.sh", SCRIPT_CONTENT)

        result = svc.read_file(SLUG, "scripts/check.sh")
        assert result == SCRIPT_CONTENT

    def test_09_build_skills_context_xml(self):
        """9. _build_skills_context() 生成包含 test-e2e 的 XML"""
        from src.services.skill_service import SkillService
        from src.ops_agent.nodes.main_agent import _build_skills_context

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)

        context = _build_skills_context(svc)
        assert "<available_skills>" in context
        assert SLUG in context
        assert "</available_skills>" in context
        assert "推荐技能" not in context

    def test_10_draft_not_in_available(self):
        """draft skill 不在 available 中"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        draft_content = SKILL_CONTENT.replace("---\n", "---\ndraft: true\n", 1)
        svc.update_skill(SLUG, draft_content)

        available = svc.get_available_skills()
        slugs = [s["slug"] for s in available]
        assert SLUG not in slugs

    def test_13_read_skill_tool(self):
        """read_skill tool 返回正确内容"""
        from src.services.skill_service import SkillService
        from src.ops_agent.nodes.main_agent import build_tools

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)
        svc.write_skill_file(SLUG, "scripts/check.sh", SCRIPT_CONTENT)

        tools = build_tools()
        read_skill = next(t for t in tools if t.name == "read_skill")

        # Read SKILL.md
        result = read_skill.invoke({"path": SLUG})
        assert "E2E 测试技能" in result
        assert "check.sh" in result

        # Read script file
        result = read_skill.invoke({"path": f"{SLUG}/scripts/check.sh"})
        assert "E2E test check" in result

    def test_14_read_skill_tool_not_found(self):
        """read_skill tool 对不存在的 skill 返回 '未找到'"""
        from src.ops_agent.nodes.main_agent import build_tools

        tools = build_tools()
        read_skill = next(t for t in tools if t.name == "read_skill")

        result = read_skill.invoke({"path": "nonexistent-skill"})
        assert "未找到" in result

    def test_15_delete_cleanup(self):
        """最终清理: 删除 skill"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.delete_skill(SLUG)
        assert all(s.slug != SLUG for s in svc.list_skills())


# ── Skill 上线检查 ─────────────────────────────────────────────


class TestSkillReadiness:
    """技能必须同时具备 name、description 和 body 才算可用。"""

    def test_incomplete_no_name_not_available(self):
        """无 name -> 不可用"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(
            SLUG, "---\nname:\ndescription: some desc\n---\n\nBody content.\n"
        )
        available = svc.get_available_skills()
        assert SLUG not in [s["slug"] for s in available]

    def test_incomplete_no_description_not_available(self):
        """无 description -> 不可用"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, "---\nname: Test\ndescription:\n---\n\nBody content.\n")
        available = svc.get_available_skills()
        assert SLUG not in [s["slug"] for s in available]

    def test_incomplete_empty_body_not_available(self):
        """空 body -> 不可用"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, "---\nname: Test\ndescription: some desc\n---\n")
        available = svc.get_available_skills()
        assert SLUG not in [s["slug"] for s in available]

    def test_complete_skill_becomes_available(self):
        """补齐后 -> 可用"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        # 先不完整
        svc.update_skill(SLUG, "---\nname:\ndescription:\n---\n")
        assert SLUG not in [s["slug"] for s in svc.get_available_skills()]
        # 补齐
        svc.update_skill(SLUG, SKILL_CONTENT)
        assert SLUG in [s["slug"] for s in svc.get_available_skills()]

    def test_draft_blocks_availability(self):
        """draft=true -> 不可用"""
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        draft_content = SKILL_CONTENT.replace("---\n", "---\ndraft: true\n", 1)
        svc.update_skill(SLUG, draft_content)
        assert SLUG not in [s["slug"] for s in svc.get_available_skills()]


# ── Agent Skill 目录上下文测试 ───────────────────────────────


class TestAgentSkillCatalogContext:
    """测试 skills_context 仅保留全量目录层。"""

    def _make_available(self, skills: list[dict]) -> list[dict]:
        """构造 available skills 列表。"""
        base = {"has_scripts": False, "has_references": False, "has_assets": False}
        return [{**base, **s} for s in skills]

    def test_build_context_includes_all_skills_without_recommendation_heading(self):
        """skills_context 只保留目录层，不包含推荐标题"""
        from src.ops_agent.nodes.main_agent import _build_skills_context
        from src.services.skill_service import SkillService

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)

        context = _build_skills_context(
            svc,
            kb_summary="mysql 告警",
            history_summary="历史上查过 redis",
            incident_description="数据库连接异常",
        )
        assert "<available_skills>" in context
        assert SLUG in context
        assert "推荐技能" not in context

    def test_build_context_uses_compact_format_above_threshold(self):
        """当 skill 数量超过阈值时，目录层使用 compact 格式但保留全量"""
        from src.ops_agent.nodes.main_agent import _build_skills_context

        available = self._make_available(
            [
                {
                    "slug": f"skill-{i:02d}",
                    "name": f"Skill {i:02d}",
                    "description": f"Description {i:02d}",
                }
                for i in range(11)
            ]
        )

        class StubSkillService:
            def get_available_skills(self):
                return available

        context = _build_skills_context(StubSkillService())
        assert '<skill name="skill-00">Description 00</skill>' in context
        assert '<skill name="skill-10">Description 10</skill>' in context
        assert "<name>skill-00</name>" not in context

    def test_build_context_keeps_all_skills_above_30(self):
        """超过 30 个 skill 时不再裁剪，仍保留全量目录"""
        from src.ops_agent.nodes.main_agent import _build_skills_context

        available = self._make_available(
            [
                {
                    "slug": f"skill-{i:02d}",
                    "name": f"Skill {i:02d}",
                    "description": f"Description {i:02d}",
                }
                for i in range(31)
            ]
        )

        class StubSkillService:
            def get_available_skills(self):
                return available

        context = _build_skills_context(StubSkillService())
        assert '<skill name="skill-00">Description 00</skill>' in context
        assert '<skill name="skill-30">Description 30</skill>' in context
        assert "还有" not in context


# ── read_skill 工具集成测试 ────────────────────────────────────


class TestReadSkillToolIntegration:
    """测试 read_skill tool 的各种调用方式。"""

    def test_build_tools_do_not_include_inventory_tools(self):
        """主 agent 不新增 list_services / inspect_server 这类 inventory tool"""
        from src.ops_agent.nodes.main_agent import build_tools

        names = [t.name for t in build_tools()]
        assert "list_services" not in names
        assert "inspect_server" not in names

    def test_catalog_then_read(self):
        """目录展示后可继续 read_skill 读取内容"""
        from src.services.skill_service import SkillService
        from src.ops_agent.nodes.main_agent import build_tools

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)

        tools = build_tools()
        read_skill = next(t for t in tools if t.name == "read_skill")
        result = read_skill.invoke({"path": SLUG})
        assert "E2E 测试技能" in result
        assert "步骤一" in result

    def test_read_question_mark_lists_all(self):
        """read_skill("?") -> 列出所有可用技能"""
        from src.services.skill_service import SkillService
        from src.ops_agent.nodes.main_agent import build_tools

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)

        tools = build_tools()
        read_skill = next(t for t in tools if t.name == "read_skill")
        result = read_skill.invoke({"path": "?"})
        assert SLUG in result
        assert "所有可用技能" in result

    def test_read_with_file_path(self):
        """read_skill("slug/scripts/check.sh") -> 脚本内容"""
        from src.services.skill_service import SkillService
        from src.ops_agent.nodes.main_agent import build_tools

        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)
        svc.write_skill_file(SLUG, "scripts/check.sh", SCRIPT_CONTENT)

        tools = build_tools()
        read_skill = next(t for t in tools if t.name == "read_skill")
        result = read_skill.invoke({"path": f"{SLUG}/scripts/check.sh"})
        assert "E2E test check" in result
