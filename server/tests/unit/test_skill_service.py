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
