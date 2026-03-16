import { test, expect } from "./fixtures/mock-api";
import {
  INCIDENT_ID,
  APPROVAL_ID_OOM,
  createMockIncident,
} from "./helpers/mock-data";
import {
  createOomPreApprovalEvents,
  createOomResumeEvents,
} from "./helpers/sse-mock";

test.describe("Agent OOM 恢复流程 — 完整审批", () => {
  test("Cron Job OOM Kill — 诊断 → 审批 → 修复 → 验证", async ({
    page,
    mockApi,
  }) => {
    const oomIncident = createMockIncident({
      title: "Cron Worker OOM Kill",
      description: "cron-worker 被 OOM killer 终止",
      severity: "high",
    });

    await Promise.all([
      mockApi.setupIncidentRoutes([oomIncident]),
      mockApi.setupGetIncident(oomIncident),
      mockApi.setupLiveSSEStream(
        createOomPreApprovalEvents(),
        createOomResumeEvents(),
      ),
      mockApi.setupApproveDecideLive(APPROVAL_ID_OOM),
      mockApi.setupMessages(),
      mockApi.setupSaveToMemory(),
    ]);

    // 从事件列表页点击进入
    await page.goto("/incidents");
    await page.getByText("Cron Worker OOM Kill").click();
    await page.waitForURL(`/incidents/${INCIDENT_ID}`);

    // 1. 子 Agent 卡片（gather_context）
    await expect(page.locator('[data-testid="event-timeline"]')).toBeVisible();
    await expect(
      page.locator('[data-testid="sub-agent-card"]'),
    ).toBeVisible();

    // 2. 诊断步骤 — 3 个 exec_read 工具调用（dmesg, free+status, systemd config）
    const toolCards = page.locator('[data-testid="tool-call-card"]');
    // Pre-approval: 3 tool_call + 3 tool_result = 6 cards
    await expect(toolCards).toHaveCount(6);

    // 3. 审批卡片出现
    await expect(page.locator('[data-testid="approval-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="risk-level"]')).toContainText(
      "MEDIUM",
    );
    // 验证审批说明
    await expect(page.locator('[data-testid="approval-card"]')).toContainText(
      "增大 cron-worker 内存限制",
    );

    // 4. 点击批准
    await page.click('[data-testid="approve-button"]');

    // 5. 等待 resume 事件 — exec_write 结果可见
    await expect(
      page.locator('[data-testid="tool-name"]').filter({ hasText: "exec_write_tool" }).first(),
    ).toBeVisible();

    // 6. 验证步骤的 exec_read 可见（MemoryLimit=3G）
    await expect(
      page.locator('[data-testid="tool-output"]').filter({ hasText: "MemoryLimit=3G" }).first(),
    ).toBeVisible();

    // 7. 排查报告
    await expect(page.locator('[data-testid="summary-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="summary-section"]')).toContainText(
      "OOM",
    );
    await expect(page.locator('[data-testid="summary-section"]')).toContainText(
      "MemoryLimit",
    );

    // 8. 保存到记忆
    await expect(
      page.locator('[data-testid="save-to-memory-btn"]'),
    ).toBeVisible();
    await page.click('[data-testid="save-to-memory-btn"]');
    await expect(
      page.locator('[data-testid="saved-to-memory"]'),
    ).toBeVisible();
  });
});
