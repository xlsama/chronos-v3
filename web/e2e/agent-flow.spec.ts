import { test, expect } from "@playwright/test";

test("完整 Agent 流程：创建事件 → 思考 → 工具调用 → 审批 → 完成", async ({
  page,
}) => {
  // 1. 打开事件列表
  await page.goto("/incidents");

  // 2. 创建新事件
  await page.click('[data-testid="create-incident-btn"]');
  await page.fill('[data-testid="incident-title"]', "Disk full on prod-01");
  await page.fill(
    '[data-testid="incident-description"]',
    "磁盘使用率超过 95%",
  );
  await page.click('[data-testid="submit-incident"]');

  // 3. 自动跳转到事件详情页
  await page.waitForURL(/\/incidents\//);

  // 4. 等待 SSE 连接
  await page.waitForSelector('[data-testid="event-timeline"]');

  // 5. 等待 Agent 思考
  await page.waitForSelector('[data-testid="thinking-bubble"]', {
    timeout: 15000,
  });

  // 6. 等待工具调用
  await page.waitForSelector('[data-testid="tool-call-card"]', {
    timeout: 15000,
  });

  // 7. 等待审批卡片
  const approvalCard = page.locator('[data-testid="approval-card"]');
  await approvalCard.waitFor({ timeout: 30000 });

  // 8. 验证风险信息展示
  await expect(page.locator('[data-testid="risk-level"]')).toBeVisible();

  // 9. 点击批准
  await page.click('[data-testid="approve-button"]');

  // 10. 等待最终报告
  await page.waitForSelector('[data-testid="summary-section"]', {
    timeout: 30000,
  });
  const summary = await page.textContent('[data-testid="summary-section"]');
  expect(summary).toBeTruthy();
});
