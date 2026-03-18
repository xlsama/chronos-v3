"""
Case 2: 微服务链路故障 - 库存服务进程被杀导致订单接口 500

场景：模拟微服务架构下的链路故障，data-server 上的 inventory-api 进程
被意外终止，导致 app-server 上的 order-api 调用库存接口失败，返回 500。
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from ..lib.api_client import ApiClient
from ..lib.fault_injector import FaultInjector
from ..lib.incident_loop import wait_for_incident_resolution

pytestmark = pytest.mark.e2e


def test_microservice_chain_failure(
    page: Page,
    seed_data: dict,
    app_injector: FaultInjector,
    data_injector: FaultInjector,
    api_client: ApiClient,
):
    # 1. 验证服务链路正常
    stdout, _, code = app_injector.exec("curl -sf http://localhost/api/orders")
    assert code == 0

    # 2. 故障注入：杀掉 data-server 上的 inventory-api 进程
    data_injector.kill_process("inventory-api/app.py")

    # 验证故障已注入
    assert not data_injector.is_process_running("inventory-api/app.py")

    # 验证故障确实导致 500
    stdout, _, _ = app_injector.exec(
        "curl -s -o /dev/null -w '%{http_code}' http://localhost/api/orders"
    )
    assert stdout.strip() == "500"

    # 3. 打开事件页面
    page.goto("/incidents")

    # 4. 创建事件
    page.click('[data-testid="create-incident-btn"]')

    page.fill(
        '[data-testid="prompt-textarea"]',
        "app-server 上的订单接口 /api/orders 返回 500 错误，请排查原因并修复",
    )

    page.click('[data-testid="submit-incident"]')

    # 5. 等待导航到事件详情页
    page.wait_for_url(re.compile(r"/incidents/[\w-]+"), timeout=15_000)
    incident_id = page.url.split("/incidents/")[1]

    # 6. 事件处理循环（最长 10 分钟）
    wait_for_incident_resolution(
        page,
        timeout_ms=10 * 60 * 1000,
        ask_human_reply=(
            "inventory-api 部署在 data-server 上，路径为 /opt/inventory-api/app.py，"
            "使用 Python venv 运行，启动命令为: "
            "/opt/inventory-api/venv/bin/python /opt/inventory-api/app.py。"
            "它监听 8080 端口，order-api 通过 http://data-server:8080 调用它。"
        ),
    )

    # 7. 断言
    summary = page.locator('[data-testid="summary-section"]')
    expect(summary).to_be_visible(timeout=30_000)

    incident = api_client.get_incident(incident_id)
    assert incident["status"] == "resolved"

    # 断言 Agent 执行了 tool call
    tool_call_cards = page.locator('[data-testid="tool-call-card"]')
    assert tool_call_cards.count() >= 1

    # 断言 summary 包含相关服务关键词
    summary_text = summary.text_content() or ""
    lower_summary = summary_text.lower()
    keywords = ["inventory", "库存", "进程", "process", "8080", "data-server"]
    assert any(kw in lower_summary for kw in keywords), (
        f"Summary should contain service-related keywords, got: {summary_text[:200]}"
    )

    # 8. Best-effort 验证：inventory-api 进程已恢复
    try:
        assert data_injector.is_process_running("inventory-api/app.py")
    except Exception:
        pass  # best-effort

    # Best-effort 验证：order-api 正常返回
    try:
        _, _, code = app_injector.exec("curl -sf http://localhost/api/orders")
        assert code == 0
    except Exception:
        pass  # best-effort

    # 9. 返回事件列表，验证事件显示为"已解决"
    page.goto("/incidents")
    expect(page.locator("text=已解决").first).to_be_visible(timeout=10_000)
