import { test, expect } from "./fixtures/mock-api";
import { INCIDENT_ID, createMockIncident } from "./helpers/mock-data";
import { createDbDiagnosticEvents } from "./helpers/sse-mock";

test.describe("Agent 诊断流程 — 纯读操作", () => {
  test("PostgreSQL 连接池耗尽 — 多步诊断无写操作", async ({
    page,
    mockApi,
  }) => {
    const dbIncident = createMockIncident({
      title: "PostgreSQL 连接池耗尽",
      description: "应用返回 503，数据库报错 too many clients already",
      severity: "critical",
    });

    await Promise.all([
      mockApi.setupIncidentRoutes([dbIncident]),
      mockApi.setupGetIncident(dbIncident),
      mockApi.setupSSEStream(createDbDiagnosticEvents()),
      mockApi.setupMessages(),
      mockApi.setupSaveToMemory(),
    ]);

    // 直接导航到事件详情页
    await page.goto(`/incidents/${INCIDENT_ID}`);

    // 1. 子 Agent 卡片出现（gather_context 阶段）
    await expect(page.locator('[data-testid="event-timeline"]')).toBeVisible();
    await expect(
      page.locator('[data-testid="sub-agent-card"]'),
    ).toBeVisible();

    // 2. 主 Agent 思考气泡（5 个 main_agent thinking，含结论）
    const thinkingBubbles = page.locator('[data-testid="thinking-bubble"]');
    await expect(thinkingBubbles).toHaveCount(5);

    // 3. 工具调用卡片（4 call + 4 result = 8 个）
    const toolCards = page.locator('[data-testid="tool-call-card"]');
    await expect(toolCards).toHaveCount(8);

    // 4. 包含 exec_read_tool 和 http_request_tool 两种工具
    const toolNames = page.locator('[data-testid="tool-name"]');
    await expect(toolNames.filter({ hasText: "exec_read_tool" })).toHaveCount(6); // 3 calls + 3 results
    await expect(toolNames.filter({ hasText: "http_request_tool" })).toHaveCount(2); // 1 call + 1 result

    // 5. 工具输出包含 pg_stat_activity 数据
    await expect(
      page.locator('[data-testid="tool-output"]').filter({ hasText: "active" }).first(),
    ).toContainText("95");

    // 6. 零个审批卡片
    await expect(page.locator('[data-testid="approval-card"]')).toHaveCount(0);

    // 7. 排查报告包含 max_connections
    await expect(page.locator('[data-testid="summary-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="summary-section"]')).toContainText(
      "max_connections",
    );

    // 8. 保存到记忆
    await expect(
      page.locator('[data-testid="save-to-memory-btn"]'),
    ).toBeVisible();
    await page.click('[data-testid="save-to-memory-btn"]');
    await expect(
      page.locator('[data-testid="saved-to-memory"]'),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="saved-to-memory"]'),
    ).toContainText("已保存到记忆");
  });
});
