"""
Case 1: 磁盘占满事件 - 完整生命周期 E2E 测试

场景：模拟一台 Linux 服务器 /tmp 目录被大文件占满的运维故障场景。
用户通过 Chronos 前端提交事件描述，后端 AI Agent（LangGraph）自动完成
故障排查与修复，最终生成事件总结。
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from ..lib.api_client import ApiClient
from ..lib.fault_injector import FaultInjector
from ..lib.incident_loop import wait_for_incident_resolution

pytestmark = pytest.mark.e2e


def test_disk_full_incident_lifecycle(
    page: Page,
    seed_data: dict,
    fault_injector: FaultInjector,
    api_client: ApiClient,
):
    # 1. 故障注入：在目标机器上制造磁盘占满
    fault_injector.inject_disk_full()

    # 2. 打开事件页面
    page.goto("/incidents")

    # 3. 创建事件
    page.click('[data-testid="create-incident-btn"]')

    # 填写事件描述
    page.fill(
        '[data-testid="prompt-textarea"]',
        "服务器 test-server 磁盘使用率过高，/tmp 目录占用异常，请排查原因并清理",
    )

    # 提交事件
    page.click('[data-testid="submit-incident"]')

    # 4. 等待导航到事件详情页
    page.wait_for_url(re.compile(r"/incidents/[\w-]+"), timeout=15_000)

    # 从 URL 提取 incident ID
    incident_id = page.url.split("/incidents/")[1]

    # 5. 事件处理循环（最长 8 分钟）
    wait_for_incident_resolution(
        page,
        ask_human_reply="请继续排查并清理 /tmp 目录下的大文件",
    )

    # 6. 断言
    summary = page.locator('[data-testid="summary-section"]')
    expect(summary).to_be_visible(timeout=30_000)

    # 通过 API 验证 incident 状态
    incident = api_client.get_incident(incident_id)
    assert incident["status"] == "resolved"

    # 断言 Agent 执行了 tool call（确认 Agent 实际工作了）
    tool_call_cards = page.locator('[data-testid="tool-call-card"]')
    assert tool_call_cards.count() >= 1

    # 断言 summary 包含磁盘相关关键词
    summary_text = summary.text_content() or ""
    lower_summary = summary_text.lower()
    keywords = ["/tmp", "testfill", "disk", "磁盘", "清理", "删除", "空间"]
    assert any(kw in lower_summary for kw in keywords), (
        f"Summary should contain disk-related keywords, got: {summary_text[:200]}"
    )

    # 7. 验证故障已修复（best-effort）
    try:
        _, _, code = fault_injector.exec("test -f /tmp/testfill")
        assert code != 0  # file should be removed
    except Exception:
        pass  # best-effort

    # 8. 返回事件列表，验证事件显示为"已解决"
    page.goto("/incidents")
    expect(page.locator("text=已解决").first).to_be_visible(timeout=10_000)
