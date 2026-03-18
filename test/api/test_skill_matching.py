"""Skill 列表与匹配测试"""

import pytest

pytestmark = pytest.mark.api


def test_get_all_summaries():
    """get_all_summaries 返回 skill 列表，每项包含 slug/name/description"""
    from src.services.skill_service import SkillService

    svc = SkillService()
    summaries = svc.get_all_summaries()
    print(f"Found {len(summaries)} skills")
    for s in summaries:
        print(f"  [{s['slug']}] {s['name']}: {s['description']}")
    assert isinstance(summaries, list)
    if len(summaries) == 0:
        pytest.skip("server/data/skills/ 目录为空，跳过结构验证")
    for s in summaries:
        assert "slug" in s
        assert "name" in s
        assert "description" in s


def test_get_auto_load_skills():
    """auto_load skills 返回 (meta, body) 元组列表"""
    from src.services.skill_service import SkillService

    svc = SkillService()
    auto_skills = svc.get_auto_load_skills()
    print(f"Found {len(auto_skills)} auto-load skills")
    for meta, body in auto_skills:
        print(f"  [{meta.slug}] {meta.name} (body: {len(body)} chars)")
    assert isinstance(auto_skills, list)
    for meta, body in auto_skills:
        assert meta.auto_load is True
        assert len(body) > 0
