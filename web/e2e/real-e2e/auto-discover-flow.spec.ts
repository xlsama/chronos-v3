import { test, expect } from "@playwright/test";
import {
  readingPause,
  thinkingPause,
  waitForBackend,
  cleanupTestData,
} from "./helpers";

const API_URL = "http://localhost:8000";

test.describe("Agent 自主发现基础设施 - Real E2E", () => {
  test.beforeAll(async () => {
    await waitForBackend(API_URL);
  });

  test.afterAll(async () => {
    await cleanupTestData(API_URL);
  });

  test("完整流程: 创建基础设施 → 创建事件 → Agent 自动发现 → 执行诊断", async ({
    page,
  }) => {
    // ── Phase 1: 创建 SSH 基础设施 ──
    await page.goto("/infrastructure");
    await readingPause();

    await page.getByRole("button", { name: "Add Infrastructure" }).click();
    await thinkingPause();

    // Fill SSH form
    await page
      .getByPlaceholder("e.g. Production Server")
      .fill("E2E Test Server");
    await thinkingPause();

    await page.getByPlaceholder("e.g. 192.168.1.1").fill("localhost");
    await thinkingPause();

    // Port - the only number input in the dialog
    const portInput = page.locator('input[type="number"]');
    await portInput.clear();
    await portInput.fill("2222");
    await thinkingPause();

    // Username - find field containing "Username" text, then its input
    const usernameInput = page
      .locator("[data-slot=field]")
      .filter({ hasText: "Username" })
      .locator("input");
    await usernameInput.clear();
    await usernameInput.fill("testuser");
    await thinkingPause();

    // Password - find field containing "Password" text, then its input
    const passwordInput = page
      .locator("[data-slot=field]")
      .filter({ hasText: "Password" })
      .locator("input");
    await passwordInput.fill("testpass");
    await thinkingPause();

    // Submit
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText("Infrastructure added")).toBeVisible({
      timeout: 10_000,
    });

    await readingPause();

    // ── Phase 2: 创建事件（不指定 infra）──
    // Navigate to incidents list first, then create via browser fetch (through Vite proxy)
    // so we can navigate to detail page BEFORE the BackgroundTask starts the Agent.
    await page.goto("/incidents");
    await readingPause();

    const incident = await page.evaluate(async () => {
      const res = await fetch("/api/incidents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: "服务器磁盘空间告警，请检查磁盘使用情况",
        }),
      });
      return res.json();
    });

    // Navigate immediately to establish SSE before Agent starts
    await page.goto(`/incidents/${incident.id}`);

    // ── Phase 3: 观察 Agent 工作 ──

    // Wait for event timeline to appear
    await expect(page.getByTestId("event-timeline")).toBeVisible({
      timeout: 30_000,
    });

    // Wait for sub-agent card (gather_context phase)
    await expect(page.getByTestId("sub-agent-card").first()).toBeVisible({
      timeout: 30_000,
    });

    // Wait for list_infrastructures tool call
    await expect(
      page
        .getByTestId("tool-name")
        .filter({ hasText: "list_infrastructures" })
        .first(),
    ).toBeVisible({ timeout: 60_000 });

    // Wait for exec_read_tool call (Agent executing commands on server)
    await expect(
      page
        .getByTestId("tool-name")
        .filter({ hasText: "exec_read_tool" })
        .first(),
    ).toBeVisible({ timeout: 60_000 });

    // Wait for summary section (Agent completed analysis)
    await expect(page.getByTestId("summary-section")).toBeVisible({
      timeout: 120_000,
    });

    // ── Phase 4: 验证结果 ──

    // Summary should have meaningful content
    const summaryText = await page
      .getByTestId("summary-section")
      .textContent();
    expect(summaryText!.length).toBeGreaterThan(50);

    // At least 4 tool calls should have been made
    const toolCount = await page.getByTestId("tool-call-card").count();
    expect(toolCount).toBeGreaterThanOrEqual(4);
  });
});
