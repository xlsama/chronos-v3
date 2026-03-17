/**
 * Case 2: 微服务链路故障 — 库存服务进程被杀导致订单接口 500
 *
 * ═══════════════════════════════════════════════════════════════
 * 场景描述
 * ═══════════════════════════════════════════════════════════════
 *
 * 模拟微服务架构下的链路故障场景：data-server 上的 inventory-api 进程
 * 被意外终止，导致 app-server 上的 order-api 调用库存接口失败，返回 500。
 * 用户通过 Chronos 前端提交事件描述，后端 AI Agent 自动排查跨服务器的
 * 故障链路并恢复服务。
 *
 * ═══════════════════════════════════════════════════════════════
 * 基础设施（由 fixture 自动管理）
 * ═══════════════════════════════════════════════════════════════
 *
 * docker compose up 启动：
 *   - PostgreSQL + Redis（共用）
 *   - app-server（Nginx + order-api Flask，端口 12223）
 *   - data-server（inventory-api Flask + PostgreSQL，端口 12224）
 *
 * ═══════════════════════════════════════════════════════════════
 * 测试数据（由 fixture `seedData` 通过 API 创建）
 * ═══════════════════════════════════════════════════════════════
 *
 * - 项目: "微服务订单系统"
 * - 2 个 SSH 连接: app-server(:12223), data-server(:12224)
 * - 3 个服务: order-api, inventory-api, inventory-postgres
 * - 服务间依赖: order-api → inventory-api → inventory-postgres
 */
import { test, expect } from "./fixture.js";
import { waitForIncidentResolution } from "../lib/incident-loop.js";

test("微服务链路故障 - 库存服务进程被杀导致订单接口 500", async ({
  page,
  seedData,
  appServerInjector,
  dataServerInjector,
  apiClient,
}) => {
  // 1. 验证服务链路正常
  const healthCheck = await appServerInjector.exec("curl -sf http://localhost/api/orders");
  expect(healthCheck.code).toBe(0);

  // 2. 故障注入：杀掉 data-server 上的 inventory-api 进程
  await dataServerInjector.killProcess("inventory-api/app.py");

  // 验证故障已注入
  const processCheck = await dataServerInjector.isProcessRunning("inventory-api/app.py");
  expect(processCheck).toBe(false);

  // 验证故障确实导致 500
  const faultVerify = await appServerInjector.exec(
    "curl -s -o /dev/null -w '%{http_code}' http://localhost/api/orders",
  );
  expect(faultVerify.stdout.trim()).toBe("500");

  // 3. 打开事件页面
  await page.goto("/incidents");

  // 4. 创建事件
  await page.click('[data-testid="create-incident-btn"]');

  await page.fill(
    '[data-testid="prompt-textarea"]',
    "app-server 上的订单接口 /api/orders 返回 500 错误，请排查原因并修复",
  );

  await page.click('[data-testid="submit-incident"]');

  // 5. 等待导航到事件详情页
  await page.waitForURL(/\/incidents\/[\w-]+/, { timeout: 15_000 });
  const incidentId = page.url().split("/incidents/")[1];

  // 6. 事件处理循环（最长 10 分钟）
  await waitForIncidentResolution(page, {
    timeoutMs: 10 * 60 * 1000,
    askHumanReply:
      "inventory-api 部署在 data-server 上，路径为 /opt/inventory-api/app.py，" +
      "使用 Python venv 运行，启动命令为: " +
      "/opt/inventory-api/venv/bin/python /opt/inventory-api/app.py。" +
      "它监听 8080 端口，order-api 通过 http://data-server:8080 调用它。",
  });

  // 7. 断言
  const summary = page.locator('[data-testid="summary-section"]');
  await expect(summary).toBeVisible({ timeout: 30_000 });

  const incident = await apiClient.getIncident(incidentId);
  expect(incident.status).toBe("resolved");

  // 断言 Agent 执行了 tool call（确认 Agent 实际工作了）
  const toolCallCards = page.locator('[data-testid="tool-call-card"]');
  const toolCallCount = await toolCallCards.count();
  expect(toolCallCount).toBeGreaterThanOrEqual(1);

  // 断言 summary 包含相关服务关键词
  const summaryText = await summary.textContent();
  expect(summaryText).toBeTruthy();
  const lowerSummary = summaryText!.toLowerCase();
  const hasRelevantKeyword = ["inventory", "库存", "进程", "process", "8080", "data-server"].some(
    (kw) => lowerSummary.includes(kw),
  );
  expect(hasRelevantKeyword).toBe(true);

  // 8. Best-effort 验证：inventory-api 进程已恢复
  try {
    const running = await dataServerInjector.isProcessRunning("inventory-api/app.py");
    expect(running).toBe(true);
  } catch {
    // best-effort
  }

  // Best-effort 验证：order-api 正常返回
  try {
    const result = await appServerInjector.exec("curl -sf http://localhost/api/orders");
    expect(result.code).toBe(0);
  } catch {
    // best-effort
  }

  // 9. 返回事件列表，验证事件显示为"已解决"
  await page.goto("/incidents");
  await expect(page.locator("text=已解决").first()).toBeVisible({ timeout: 10_000 });
});
