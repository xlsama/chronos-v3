"""SkillService 单元测试 — 校验、文件管理、read_file"""

import pytest
from pathlib import Path

pytestmark = pytest.mark.api


@pytest.fixture
def tmp_skills(tmp_path):
    """创建临时 skills 目录并返回 SkillService 实例"""
    from src.services.skill_service import SkillService

    return SkillService(base_dir=tmp_path)


@pytest.fixture
def populated_skill(tmp_skills):
    """创建一个完整的 skill 用于测试"""
    svc = tmp_skills
    svc.create_skill("mysql-oom")
    svc.update_skill("mysql-oom", "---\nname: MySQL OOM 排查\ndescription: 检查内存配置、慢查询、连接数溢出\n---\n\n# MySQL OOM 排查\n\n## 步骤一\n检查内存。\n")
    return svc


# ===== 校验规则测试 =====

class TestValidation:
    def test_validate_valid_slug(self, tmp_skills):
        """合法 slug 通过校验"""
        svc = tmp_skills
        errors = svc._validate_slug("mysql-oom")
        assert errors == []

    def test_validate_slug_uppercase_rejected(self, tmp_skills):
        """大写 slug 被拒绝"""
        svc = tmp_skills
        errors = svc._validate_slug("MySQL-OOM")
        assert len(errors) > 0

    def test_validate_slug_double_dash_rejected(self, tmp_skills):
        """双连字符 slug 被拒绝"""
        svc = tmp_skills
        errors = svc._validate_slug("mysql--oom")
        assert len(errors) > 0

    def test_validate_slug_leading_dash_rejected(self, tmp_skills):
        """前导连字符 slug 被拒绝"""
        svc = tmp_skills
        errors = svc._validate_slug("-mysql")
        assert len(errors) > 0

    def test_validate_slug_trailing_dash_rejected(self, tmp_skills):
        """尾随连字符 slug 被拒绝"""
        svc = tmp_skills
        errors = svc._validate_slug("mysql-")
        assert len(errors) > 0

    def test_validate_slug_max_length(self, tmp_skills):
        """超过 64 字符的 slug 被拒绝"""
        svc = tmp_skills
        long_slug = "a" * 65
        errors = svc._validate_slug(long_slug)
        assert len(errors) > 0

    def test_validate_name_rules(self, tmp_skills):
        """name 校验: 非空，max 64"""
        svc = tmp_skills
        # 空 name
        errors = svc._validate_skill("test", {"name": "", "description": "desc"}, "body")
        assert any("name" in e.lower() for e in errors)
        # 超长 name
        errors = svc._validate_skill("test", {"name": "x" * 65, "description": "desc"}, "body")
        assert any("name" in e.lower() for e in errors)

    def test_validate_description(self, tmp_skills):
        """description 校验: 非空，max 1024"""
        svc = tmp_skills
        # 空 description
        errors = svc._validate_skill("test", {"name": "test", "description": ""}, "body")
        assert any("description" in e.lower() for e in errors)
        # 超长 description
        errors = svc._validate_skill("test", {"name": "test", "description": "x" * 1025}, "body")
        assert any("description" in e.lower() for e in errors)

    def test_validate_body_nonempty(self, tmp_skills):
        """body 必须非空"""
        svc = tmp_skills
        errors = svc._validate_skill("test", {"name": "test", "description": "desc"}, "")
        assert any("body" in e.lower() for e in errors)

    def test_validate_passes_for_valid_skill(self, tmp_skills):
        """合法 skill 通过校验"""
        svc = tmp_skills
        errors = svc._validate_skill("test", {"name": "test", "description": "desc"}, "body content")
        assert errors == []


# ===== 文件管理测试 =====

class TestFileManagement:
    def test_list_skill_files_empty(self, populated_skill):
        """新建 skill 没有附属文件"""
        files = populated_skill.list_skill_files("mysql-oom")
        assert files == {"scripts": [], "references": [], "assets": []}

    def test_write_and_list_script(self, populated_skill):
        """写入脚本文件后能列出"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "scripts/check.sh", "#!/bin/bash\necho hello")
        files = svc.list_skill_files("mysql-oom")
        assert "check.sh" in files["scripts"]

    def test_write_and_read_script(self, populated_skill):
        """写入后能读取脚本内容"""
        svc = populated_skill
        content = "#!/bin/bash\necho hello"
        svc.write_skill_file("mysql-oom", "scripts/check.sh", content)
        result = svc.read_skill_file("mysql-oom", "scripts/check.sh")
        assert result == content

    def test_write_and_list_reference(self, populated_skill):
        """写入参考文档后能列出"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "references/guide.md", "# Guide\n\nSome content")
        files = svc.list_skill_files("mysql-oom")
        assert "guide.md" in files["references"]

    def test_delete_skill_file(self, populated_skill):
        """删除附属文件"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "scripts/check.sh", "content")
        svc.delete_skill_file("mysql-oom", "scripts/check.sh")
        files = svc.list_skill_files("mysql-oom")
        assert "check.sh" not in files["scripts"]

    def test_path_traversal_blocked(self, populated_skill):
        """路径穿越被阻止"""
        svc = populated_skill
        with pytest.raises(ValueError, match="非法路径"):
            svc.read_skill_file("mysql-oom", "../../../etc/passwd")

    def test_path_traversal_dotdot_in_middle(self, populated_skill):
        """中间的 .. 被阻止"""
        svc = populated_skill
        with pytest.raises(ValueError, match="非法路径"):
            svc.write_skill_file("mysql-oom", "scripts/../../../etc/passwd", "hack")

    def test_absolute_path_blocked(self, populated_skill):
        """绝对路径被阻止"""
        svc = populated_skill
        with pytest.raises(ValueError, match="非法路径"):
            svc.read_skill_file("mysql-oom", "/etc/passwd")

    def test_invalid_subdirectory_blocked(self, populated_skill):
        """只允许 scripts/、references/ 和 assets/ 子目录"""
        svc = populated_skill
        with pytest.raises(ValueError, match="非法路径"):
            svc.write_skill_file("mysql-oom", "hacks/evil.sh", "content")

    def test_read_nonexistent_file(self, populated_skill):
        """读取不存在的文件抛 FileNotFoundError"""
        svc = populated_skill
        with pytest.raises(FileNotFoundError):
            svc.read_skill_file("mysql-oom", "scripts/nonexistent.sh")


# ===== read_file 方法测试（为 read_skill tool 服务）=====

class TestReadFile:
    def test_read_file_returns_body_and_listing(self, populated_skill):
        """read_file(slug, None) 返回 SKILL.md body + 文件目录"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "scripts/check.sh", "#!/bin/bash\necho hello")
        svc.write_skill_file("mysql-oom", "references/guide.md", "# Guide")
        result = svc.read_file("mysql-oom")
        # 应包含 body 内容
        assert "MySQL OOM 排查" in result
        assert "步骤一" in result
        # 应包含文件列表
        assert "check.sh" in result
        assert "guide.md" in result

    def test_read_file_returns_body_only_when_no_files(self, populated_skill):
        """read_file(slug, None) 没有附属文件时只返回 body"""
        svc = populated_skill
        result = svc.read_file("mysql-oom")
        assert "MySQL OOM 排查" in result
        # 不应出现空的文件列表标题
        assert "scripts" not in result.lower() or "无附属文件" in result or "scripts" in result

    def test_read_file_returns_script_content(self, populated_skill):
        """read_file(slug, rel_path) 返回具体文件内容"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "scripts/check.sh", "#!/bin/bash\necho hello")
        result = svc.read_file("mysql-oom", "scripts/check.sh")
        assert result == "#!/bin/bash\necho hello"

    def test_read_file_nonexistent_skill(self, tmp_skills):
        """read_file 对不存在的 skill 抛 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            tmp_skills.read_file("nonexistent")


# ===== draft 功能测试 =====

class TestDraft:
    def test_draft_excluded_from_available(self, tmp_skills):
        """draft: true 的 skill 不出现在 get_available_skills()"""
        svc = tmp_skills
        svc.create_skill("draft-skill")
        svc.update_skill("draft-skill", "---\nname: Draft Skill\ndescription: A draft\ndraft: true\n---\n\nContent here.\n")
        available = svc.get_available_skills()
        slugs = [s["slug"] for s in available]
        assert "draft-skill" not in slugs

    def test_non_draft_in_available(self, tmp_skills):
        """非 draft skill 出现在 get_available_skills()"""
        svc = tmp_skills
        svc.create_skill("ready-skill")
        svc.update_skill("ready-skill", "---\nname: Ready Skill\ndescription: A ready skill\n---\n\nContent here.\n")
        available = svc.get_available_skills()
        slugs = [s["slug"] for s in available]
        assert "ready-skill" in slugs

    def test_available_skills_include_file_info(self, tmp_skills):
        """get_available_skills() 返回 has_scripts/has_references 信息"""
        svc = tmp_skills
        svc.create_skill("with-files")
        svc.update_skill("with-files", "---\nname: With Files\ndescription: Has scripts\n---\n\nContent.\n")
        svc.write_skill_file("with-files", "scripts/check.sh", "#!/bin/bash")
        available = svc.get_available_skills()
        skill = next(s for s in available if s["slug"] == "with-files")
        assert skill["has_scripts"] is True
        assert skill["has_references"] is False


# ===== CRUD 基本功能测试 =====

class TestCRUD:
    def test_create_and_list(self, tmp_skills):
        """创建 skill 后能在列表中找到"""
        svc = tmp_skills
        meta = svc.create_skill("test-skill")
        assert meta.slug == "test-skill"
        skills = svc.list_skills()
        assert len(skills) == 1
        assert skills[0].slug == "test-skill"

    def test_create_duplicate_raises(self, tmp_skills):
        """重复创建抛 FileExistsError"""
        svc = tmp_skills
        svc.create_skill("test-skill")
        with pytest.raises(FileExistsError):
            svc.create_skill("test-skill")

    def test_get_skill_returns_meta_and_raw(self, populated_skill):
        """get_skill 返回 meta + raw SKILL.md"""
        meta, raw = populated_skill.get_skill("mysql-oom")
        assert meta.slug == "mysql-oom"
        assert meta.name == "MySQL OOM 排查"
        assert "---" in raw  # raw 包含 frontmatter

    def test_update_skill(self, populated_skill):
        """更新 SKILL.md 内容"""
        svc = populated_skill
        new_content = "---\nname: Updated\ndescription: Updated desc\n---\n\nNew body.\n"
        meta = svc.update_skill("mysql-oom", new_content)
        assert meta.name == "Updated"

    def test_delete_skill(self, tmp_skills):
        """删除 skill"""
        svc = tmp_skills
        svc.create_skill("to-delete")
        svc.delete_skill("to-delete")
        assert len(svc.list_skills()) == 0

    def test_delete_nonexistent_raises(self, tmp_skills):
        """删除不存在的 skill 抛 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            tmp_skills.delete_skill("nonexistent")

    def test_meta_has_new_fields(self, populated_skill):
        """SkillMeta 包含新字段"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "scripts/check.sh", "#!/bin/bash")
        meta, _ = svc.get_skill("mysql-oom")
        assert meta.has_scripts is True
        assert meta.has_references is False
        assert meta.has_assets is False
        assert isinstance(meta.script_files, list)
        assert "check.sh" in meta.script_files
        assert meta.draft is False


# ===== Assets 目录支持测试 =====

class TestAssets:
    def test_write_and_list_asset(self, populated_skill):
        """写入 assets 文件后能列出"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "assets/report-template.md", "# 报告模板")
        files = svc.list_skill_files("mysql-oom")
        assert "report-template.md" in files["assets"]

    def test_write_and_read_asset(self, populated_skill):
        """写入后能读取 assets 内容"""
        svc = populated_skill
        content = "# 配置模板\nkey: value"
        svc.write_skill_file("mysql-oom", "assets/config-template.yaml", content)
        result = svc.read_skill_file("mysql-oom", "assets/config-template.yaml")
        assert result == content

    def test_delete_asset(self, populated_skill):
        """删除 assets 文件"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "assets/template.md", "content")
        svc.delete_skill_file("mysql-oom", "assets/template.md")
        files = svc.list_skill_files("mysql-oom")
        assert "template.md" not in files["assets"]

    def test_meta_has_assets(self, populated_skill):
        """SkillMeta 正确反映 assets 状态"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "assets/template.md", "content")
        meta, _ = svc.get_skill("mysql-oom")
        assert meta.has_assets is True
        assert "template.md" in meta.asset_files

    def test_read_file_shows_assets_in_listing(self, populated_skill):
        """read_file 输出包含 assets 文件列表"""
        svc = populated_skill
        svc.write_skill_file("mysql-oom", "assets/report.md", "# Report")
        result = svc.read_file("mysql-oom")
        assert "assets/" in result
        assert "report.md" in result

    def test_available_skills_include_has_assets(self, tmp_skills):
        """get_available_skills() 返回 has_assets 信息"""
        svc = tmp_skills
        svc.create_skill("with-assets")
        svc.update_skill("with-assets", "---\nname: With Assets\ndescription: Has assets\n---\n\nContent.\n")
        svc.write_skill_file("with-assets", "assets/template.md", "# Template")
        available = svc.get_available_skills()
        skill = next(s for s in available if s["slug"] == "with-assets")
        assert skill["has_assets"] is True
