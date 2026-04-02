from src.ops_agent.tools.readonly_tools import SkillReadTool
from src.lib.paths import seeds_skills_dir
from src.services.skill_service import SkillService


def test_seed_database_skill_is_available_and_readable():
    service = SkillService(base_dir=seeds_skills_dir())

    available = {skill["slug"]: skill for skill in service.get_available_skills()}

    assert "database" in available
    assert "数据库" in available["database"]["description"]

    content = service.read_file("database")

    assert "service_exec" in content
    assert "ssh_bash" in content


def test_read_file_attached_file_hint_uses_skill_read(tmp_path):
    skill_dir = tmp_path / "demo-skill"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Demo Skill\ndescription: Demo desc\n---\n\nDemo body\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "check.sh").write_text("echo ok\n", encoding="utf-8")

    service = SkillService(base_dir=tmp_path)
    content = service.read_file("demo-skill")

    assert 'skill_read("{slug}/{path}")' in content
    assert "scripts/check.sh" in content


def test_skill_read_tool_name():
    assert SkillReadTool().name == "skill_read"
