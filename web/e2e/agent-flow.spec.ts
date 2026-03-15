import { test, expect } from "./fixtures/mock-api";
import { INCIDENT_ID } from "./helpers/mock-data";

test.describe("Agent 完整流程", () => {
  test("完整场景：创建事件 → 子 Agent → 主 Agent → 审批 → 报告 → 保存到记忆", async ({
    page,
    mockApi,
  }) => {
    // Use live SSE — connection stays open, no reload needed
    await mockApi.setupAllLive();
    await page.goto("/incidents");

    // 1. 创建事件
    await page.click('[data-testid="create-incident-btn"]');
    await page.fill('[data-testid="prompt-textarea"]', "Nginx 服务异常 生产环境 502 错误");
    await page.click('[data-testid="submit-incident"]');
    await page.waitForURL(`/incidents/${INCIDENT_ID}`);

    // 2. 子 Agent 卡片出现（gather_context 阶段）
    await expect(page.locator('[data-testid="event-timeline"]')).toBeVisible();
    await expect(
      page.locator('[data-testid="sub-agent-card"]'),
    ).toBeVisible();

    // 3. 主 Agent 思考
    await expect(
      page.locator('[data-testid="thinking-bubble"]').first(),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="thinking-bubble"]').first(),
    ).toContainText("让我分析");

    // 4. 工具调用
    await expect(
      page.locator('[data-testid="tool-call-card"]').first(),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="tool-name"]').first(),
    ).toContainText("exec_read_tool");

    // 5. 审批 → 点击批准
    await expect(page.locator('[data-testid="approval-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="risk-level"]')).toContainText(
      "MEDIUM",
    );
    await page.click('[data-testid="approve-button"]');

    // Approval triggers resume events on the SAME SSE connection (no reload)

    // 6. 等待报告（在同一连接上推送过来）
    await expect(page.locator('[data-testid="summary-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="summary-section"]')).toContainText(
      "排查报告",
    );

    // 7. 点击"添加到记忆"
    await expect(
      page.locator('[data-testid="save-to-memory-btn"]'),
    ).toBeVisible();
    await page.click('[data-testid="save-to-memory-btn"]');

    // 8. 验证已保存状态
    await expect(
      page.locator('[data-testid="saved-to-memory"]'),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="saved-to-memory"]'),
    ).toContainText("已保存到记忆");
  });

  test("拒绝审批请求", async ({ page, mockApi }) => {
    await mockApi.setupAll();
    await page.goto(`/incidents/${INCIDENT_ID}`);

    await expect(page.locator('[data-testid="approval-card"]')).toBeVisible();
    await page.click('[data-testid="reject-button"]');
    await expect(page.getByText("Request rejected")).toBeVisible();
  });
});
