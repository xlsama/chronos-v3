"""全链路 E2E 测试：知识库 + 服务器 + Skill + 事件触发 + Agent 排查"""

import re
import time

import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

BASE_URL = "http://localhost:5173"
API_URL = "http://localhost:8000"

SKILL_SLUG = "kfc-alert-check"
PROJECT_NAME = "KFC 监控系统"
SERVER_NAME = "KFC 后端服务器"

SKILL_CONTENT = """\
---
name: KFC 告警排查
description: KFC 门店监控系统告警排查，检查告警状态、设备异常、门店运营情况
---

# KFC 告警排查

当收到 KFC 门店监控相关告警时，按以下步骤排查。

## 步骤一：查看未解决告警
SSH 到服务器，连接数据库查看当前未解决告警：
```bash
psql -h localhost -U kfc -d kfc_monitor -c "SELECT a.id, a.level, a.title, s.name AS store_name FROM alerts a JOIN stores s ON a.store_id = s.id WHERE a.status = 'open' ORDER BY a.created_at DESC LIMIT 10;"
```
密码: 123456

## 步骤二：检查设备状态
查看异常设备：
```bash
psql -h localhost -U kfc -d kfc_monitor -c "SELECT e.name, e.type, e.status, s.name AS store_name FROM equipment e JOIN stores s ON e.store_id = s.id WHERE e.status != 'normal';"
```

## 步骤三：总结
根据查询结果，汇总告警和设备异常情况，给出处理建议。
"""

INCIDENT_PROMPT = "KFC 门店监控系统告警：广州天河店 POS 设备异常，请排查告警情况"

README_PATH = "/Users/xlsama/w/kfc-monitor/docs/README.md"


def _cleanup_resources():
    """通过 API 清理残留的测试资源"""
    client = httpx.Client(base_url=API_URL, timeout=10)

    # 删除 skill
    client.delete(f"/api/skills/{SKILL_SLUG}")

    # 删除 project (find by name)
    try:
        resp = client.get("/api/projects", params={"page_size": 100})
        if resp.status_code == 200:
            for p in resp.json().get("items", []):
                if p["name"] == PROJECT_NAME:
                    client.delete(f"/api/projects/{p['id']}")
    except Exception:
        pass

    # 删除 server (find by name)
    try:
        resp = client.get("/api/servers", params={"page_size": 100})
        if resp.status_code == 200:
            for s in resp.json().get("items", []):
                if s["name"] == SERVER_NAME:
                    client.delete(f"/api/servers/{s['id']}")
    except Exception:
        pass

    client.close()


@pytest.fixture(autouse=True)
def cleanup():
    """测试前后清理"""
    _cleanup_resources()
    yield
    _cleanup_resources()


def test_full_skill_pipeline(page: Page):
    """完整流程: 创建知识库 → 添加服务器 → 创建 Skill → 触发事件 → 验证 skill_read"""

    # ── Step 1: 创建知识库项目 + 上传文档 ──────────────────────────

    page.goto(f"{BASE_URL}/projects")
    page.wait_for_load_state("networkidle")

    # 点击 "新建项目"
    page.get_by_role("button", name="新建项目").click()

    # 填写项目名称和描述
    page.get_by_placeholder("项目名称").fill(PROJECT_NAME)
    page.get_by_placeholder("描述（选填）").fill("KFC 门店监控系统运维手册")

    # 点击对话框中的 "创建" 按钮
    page.locator("[role=dialog]").get_by_role("button", name="创建").click()

    # 等待跳转到项目详情页
    page.wait_for_url(re.compile(r"/projects/[0-9a-f-]+"), timeout=10000)
    page.wait_for_load_state("networkidle")

    # 上传 README.md 文件
    page.locator('input[type="file"]').set_input_files(README_PATH)

    # 等待文档出现并完成索引（轮询最多 30 秒）
    expect(page.get_by_text("已索引")).to_be_visible(timeout=30000)

    # ── Step 2: 添加 SSH 服务器 ──────────────────────────────────

    page.goto(f"{BASE_URL}/connections")
    page.wait_for_load_state("networkidle")

    # 点击 "添加连接" 下拉按钮
    page.get_by_role("button", name="添加连接").click()

    # 选择 "添加服务器"
    page.get_by_text("添加服务器", exact=False).first.click()

    # 等待对话框出现
    page.locator("[role=dialog]").wait_for(state="visible")

    # 填写服务器信息
    page.get_by_placeholder("例如: 生产服务器").fill(SERVER_NAME)
    page.get_by_placeholder("e.g. 192.168.1.1").fill("localhost")

    # 修改端口: 清空默认值 22，填入 2222
    port_input = page.locator("[role=dialog]").locator('input[type="number"]').first
    port_input.fill("2222")

    # 用户名保持默认 root

    # 填写密码
    page.locator("[role=dialog]").locator('input[type="password"]').fill("123456")

    # 点击 "添加" 按钮
    page.locator('button[type="submit"][form="server-form"]').click()

    # 等待对话框关闭（服务器添加成功）
    page.locator("[role=dialog]").wait_for(state="hidden", timeout=10000)

    # ── Step 3: 创建 Skill ───────────────────────────────────────

    page.goto(f"{BASE_URL}/skills")
    page.wait_for_load_state("networkidle")

    # 点击 "创建技能"
    page.get_by_role("button", name="创建技能").click()

    # 填写 slug
    page.get_by_placeholder("例如: mysql-oom").fill(SKILL_SLUG)

    # 点击对话框 "创建" 按钮
    page.locator("[role=dialog]").get_by_role("button", name="创建").click()

    # 等待跳转到 skill 详情页
    page.wait_for_url(re.compile(f"/skills/{SKILL_SLUG}"), timeout=10000)
    page.wait_for_load_state("networkidle")

    # 点击 "编辑" 按钮
    page.get_by_role("button", name="编辑").click()

    # 输入 SKILL.md 内容
    editor = page.locator("textarea").first
    editor.fill(SKILL_CONTENT)

    # 保存
    page.get_by_role("button", name="保存").click()
    page.wait_for_load_state("networkidle")

    # 验证标题更新
    expect(
        page.get_by_role("heading", name="KFC 告警排查").first
    ).to_be_visible(timeout=5000)

    # ── Step 4: 创建事件，触发 Agent ─────────────────────────────

    page.goto(f"{BASE_URL}/incidents")
    page.wait_for_load_state("networkidle")

    # 点击 "新建事件"
    page.locator('[data-testid="create-incident-btn"]').click()

    # 等待对话框出现
    page.locator("[role=dialog]").wait_for(state="visible")

    # 输入事件描述
    page.locator('[data-testid="prompt-textarea"]').fill(INCIDENT_PROMPT)

    # 点击发送
    page.locator('[data-testid="submit-incident"]').click()

    # 等待跳转到事件详情页
    page.wait_for_url(re.compile(r"/incidents/[0-9a-f-]+"), timeout=15000)
    page.wait_for_load_state("networkidle")

    # ── Step 5: 等待知识库确认并点击 ─────────────────────────────

    # 等待时间线出现
    page.locator('[data-testid="event-timeline"]').wait_for(
        state="visible", timeout=30000
    )

    # Agent 收集上下文后会弹出 KB 确认卡片，等待 "确认" 按钮出现并点击
    confirm_btn = page.get_by_role("button", name="确认")
    confirm_btn.wait_for(state="visible", timeout=60000)
    confirm_btn.click()

    # ── Step 6: 等待并验证 skill_read 事件 ───────────────────────

    # 等待 "读取技能：" 文本出现（包含 LLM 推理时间，最多 120 秒）
    skill_read_text = page.get_by_text("读取技能：")
    skill_read_text.wait_for(state="visible", timeout=120000)

    # 验证 skill 名称出现（CollapsibleTrigger 按钮中）
    skill_trigger = page.get_by_role("button", name="kfc-alert-check").or_(
        page.get_by_role("button", name="KFC 告警排查")
    )
    expect(skill_trigger).to_be_visible(timeout=5000)

    # 点击展开 Collapsible
    skill_trigger.click()

    # 验证展开后能看到 skill 内容关键词
    expect(page.get_by_text("步骤一")).to_be_visible(timeout=5000)

    # 再次点击收起
    skill_trigger.click()
    page.wait_for_timeout(500)

    # ── Step 7: 等待 Agent 完成或超时 ────────────────────────────

    # 等待 answer 卡片出现，最多 120 秒
    try:
        page.get_by_text("排查结论", exact=False).or_(
            page.get_by_text("总结", exact=False)
        ).wait_for(state="visible", timeout=120000)
    except Exception:
        # Agent 可能还在运行，但 skill_read 已验证通过
        pass

    # 测试成功：skill_read + collapsible UI 已验证
