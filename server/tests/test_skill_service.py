from src.lib.paths import seeds_skills_dir
from src.services.skill_service import SkillService


def test_seed_incident_triage_skill_is_available_and_readable():
    service = SkillService(base_dir=seeds_skills_dir())

    available = {skill["slug"]: skill for skill in service.get_available_skills()}

    assert "incident-triage" in available
    assert "通用运维排障分诊骨架" in available["incident-triage"]["description"]

    content = service.read_file("incident-triage")

    assert "症状归类" in content
    assert "目标锁定" in content
