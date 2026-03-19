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

    def test_12_recommend_skills(self):
        """推荐机制根据上下文关键词匹配"""
        from src.services.skill_service import SkillService
        from src.ops_agent.nodes.main_agent import _recommend_skills

        svc = SkillService()
        available = [
            {"slug": "mysql-oom", "name": "MySQL OOM", "description": "MySQL 内存溢出排查", "has_scripts": False, "has_references": False},
            {"slug": "redis-latency", "name": "Redis Latency", "description": "Redis 高延迟排查", "has_scripts": False, "has_references": False},
        ]
        recommended = _recommend_skills(available, "MySQL 数据库 OOM 告警", None)
        slugs = [s["slug"] for s in recommended]
        assert "mysql-oom" in slugs

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
        svc.update_skill(SLUG, "---\nname:\ndescription: some desc\n---\n\nBody content.\n")
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


# ── Agent 模糊匹配测试 ───────────────────────────────────────

class TestAgentSkillMatching:
    """测试 _recommend_skills 的关键词匹配逻辑。"""

    def _make_available(self, skills: list[dict]) -> list[dict]:
        """构造 available skills 列表。"""
        base = {"has_scripts": False, "has_references": False, "has_assets": False}
        return [{**base, **s} for s in skills]

    def test_exact_keyword_match(self):
        """slug="mysql-oom", context 含 "mysql" -> 匹配"""
        from src.ops_agent.nodes.main_agent import _recommend_skills
        available = self._make_available([
            {"slug": "mysql-oom", "name": "MySQL OOM", "description": "MySQL 内存溢出排查"},
        ])
        result = _recommend_skills(available, "MySQL 数据库告警", None)
        assert "mysql-oom" in [s["slug"] for s in result]

    def test_vague_context_partial_match(self):
        """slug="redis-latency", context="Redis 缓存响应慢" -> 匹配 ("redis" in context)"""
        from src.ops_agent.nodes.main_agent import _recommend_skills
        available = self._make_available([
            {"slug": "redis-latency", "name": "Redis Latency", "description": "Redis 高延迟排查"},
        ])
        result = _recommend_skills(available, "Redis 缓存响应慢", None)
        assert "redis-latency" in [s["slug"] for s in result]

    def test_no_match_irrelevant_context(self):
        """slug="mysql-oom", context="Nginx 502" -> 不匹配"""
        from src.ops_agent.nodes.main_agent import _recommend_skills
        available = self._make_available([
            {"slug": "mysql-oom", "name": "MySQL OOM", "description": "MySQL 内存溢出排查"},
        ])
        result = _recommend_skills(available, "Nginx 502 错误", None)
        assert "mysql-oom" not in [s["slug"] for s in result]

    def test_short_keywords_skipped(self):
        """slug="db-oom", "db" len=2 被跳过，"oom" len=3 可匹配"""
        from src.ops_agent.nodes.main_agent import _recommend_skills
        available = self._make_available([
            {"slug": "db-oom", "name": "DB OOM", "description": "数据库内存溢出"},
        ])
        # "db" 太短被跳过，但 "oom" 可匹配
        result = _recommend_skills(available, "服务器 OOM 告警", None)
        assert "db-oom" in [s["slug"] for s in result]
        # 只含 "db" 则不匹配
        result = _recommend_skills(available, "数据库连接异常", None)
        assert "db-oom" not in [s["slug"] for s in result]

    def test_history_summary_contributes(self):
        """kb=None, history 含关键词 -> 匹配"""
        from src.ops_agent.nodes.main_agent import _recommend_skills
        available = self._make_available([
            {"slug": "mysql-oom", "name": "MySQL OOM", "description": "MySQL 内存溢出排查"},
        ])
        result = _recommend_skills(available, None, "历史：MySQL 服务器 OOM killed")
        assert "mysql-oom" in [s["slug"] for s in result]

    def test_max_3_recommended(self):
        """创建 5 个匹配 skill -> 只推荐 3 个"""
        from src.ops_agent.nodes.main_agent import _recommend_skills
        available = self._make_available([
            {"slug": f"mysql-check{i}", "name": f"MySQL Check {i}", "description": f"MySQL 检查 {i}"}
            for i in range(5)
        ])
        result = _recommend_skills(available, "mysql 数据库问题", None)
        assert len(result) <= 3

    def test_build_context_includes_matched(self):
        """_build_skills_context 包含推荐 skill"""
        from src.services.skill_service import SkillService
        from src.ops_agent.nodes.main_agent import _build_skills_context
        svc = SkillService()
        svc.create_skill(SLUG)
        svc.update_skill(SLUG, SKILL_CONTENT)
        context = _build_skills_context(svc)
        assert "<available_skills>" in context
        assert SLUG in context


# ── read_skill 工具集成测试 ────────────────────────────────────

class TestReadSkillToolIntegration:
    """测试 read_skill tool 的各种调用方式。"""

    def test_recommend_then_read(self):
        """推荐 -> read_skill 读取 -> 返回内容"""
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
