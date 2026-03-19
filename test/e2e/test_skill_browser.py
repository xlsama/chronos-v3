"""Skill 系统 Playwright E2E 测试 — 浏览器端完整流程"""

import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

BASE_URL = "http://localhost:5173"
API_URL = "http://localhost:8000"
SLUG = "pw-e2e-test"


@pytest.fixture(autouse=True)
def cleanup():
    """测试前后清理"""
    import httpx

    httpx.delete(f"{API_URL}/api/skills/{SLUG}", timeout=5)
    yield
    httpx.delete(f"{API_URL}/api/skills/{SLUG}", timeout=5)


def test_skill_full_lifecycle(page: Page):
    """完整生命周期: 创建 → 编辑 SKILL.md → 添加脚本文件 → 验证文件树 → 删除"""

    # 1. 进入技能列表页
    page.goto(f"{BASE_URL}/skills")
    page.wait_for_load_state("networkidle")

    # 2. 点击 "创建技能"
    page.get_by_role("button", name="创建技能").click()

    # 3. 填写 slug 并提交
    page.get_by_placeholder("例如: mysql-oom").fill(SLUG)
    # 点击对话框中的创建按钮（非页面上的"创建技能"）
    page.locator("[role=dialog]").get_by_role("button", name="创建").click()

    # 4. 应自动跳转到详情页
    page.wait_for_url(re.compile(f"/skills/{SLUG}"))
    page.wait_for_load_state("networkidle")

    # 5. 验证文件树中有 SKILL.md
    expect(page.get_by_role("button", name="SKILL.md")).to_be_visible()

    # 6. 点击编辑 SKILL.md
    page.get_by_role("button", name="编辑").click()

    # 7. 输入内容
    editor = page.locator("textarea").first
    editor.fill(
        "---\n"
        "name: Playwright 测试技能\n"
        "description: 浏览器端自动化测试创建的技能\n"
        "---\n\n"
        "# Playwright 测试技能\n\n"
        "## 步骤一\n"
        "执行 `free -m` 检查内存。\n"
    )

    # 8. 保存
    page.get_by_role("button", name="保存").click()
    page.wait_for_load_state("networkidle")

    # 9. 验证标题更新（header 中的 h1）
    expect(page.get_by_role("heading", name="Playwright 测试技能").first).to_be_visible()

    # 10. 添加脚本文件
    page.get_by_text("添加文件").click()

    # 填写文件名（目录默认是 scripts/）
    page.get_by_placeholder("文件名").fill("check.sh")
    page.locator("[role=dialog]").get_by_role("button", name="创建").click()

    # 11. 应进入脚本文件编辑模式，顶部显示路径
    expect(page.locator("span", has_text="scripts/check.sh")).to_be_visible()

    # 12. 输入脚本内容并保存
    file_editor = page.locator("textarea").first
    file_editor.fill("#!/bin/bash\necho 'Playwright E2E check'\nfree -m")

    page.get_by_role("button", name="保存").click()
    page.wait_for_load_state("networkidle")

    # 13. 等待 skill 数据刷新（文件保存后 invalidateQueries）
    page.wait_for_timeout(500)

    # 14. 切回 SKILL.md（用文件树中的按钮，排除 toast 干扰）
    page.get_by_role("button", name="SKILL.md").click()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading", name="Playwright 测试技能").first).to_be_visible()

    # 15. 通过 API 验证数据完整性
    import httpx

    resp = httpx.get(f"{API_URL}/api/skills/{SLUG}", timeout=5)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Playwright 测试技能"
    assert data["has_scripts"] is True
    assert "check.sh" in data["script_files"]

    resp = httpx.get(f"{API_URL}/api/skills/{SLUG}/files/scripts/check.sh", timeout=5)
    assert resp.status_code == 200
    assert "Playwright E2E check" in resp.json()["content"]

    # 16. 返回列表页
    page.locator("a[href='/skills']").first.click()
    page.wait_for_url(re.compile("/skills$"))
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Playwright 测试技能")).to_be_visible()

    # 17. 进入详情页删除
    page.get_by_text("Playwright 测试技能").click()
    page.wait_for_url(re.compile(f"/skills/{SLUG}"))
    page.wait_for_load_state("networkidle")

    page.get_by_role("button", name="删除").first.click()
    # 确认对话框中的删除按钮
    page.locator("[role=alertdialog]").get_by_role("button", name="删除").click()

    # 18. 跳转回列表页，技能不再存在
    page.wait_for_url(re.compile("/skills$"))
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Playwright 测试技能")).not_to_be_visible()
