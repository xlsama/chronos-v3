import { test, expect } from "./fixtures/mock-api";
import { INCIDENT_ID, createMockIncident } from "./helpers/mock-data";
import { createErrorEvents } from "./helpers/sse-mock";

test.describe("错误场景", () => {
  test("SSE 推送 error 事件时显示错误信息", async ({ page, mockApi }) => {
    await mockApi.setupGetIncident();
    await mockApi.setupSSEStream(createErrorEvents());
    await mockApi.setupMessages();
    await page.goto(`/incidents/${INCIDENT_ID}`);

    await expect(page.getByText("Agent 执行过程中发生错误：连接超时")).toBeVisible();
  });

  test("创建事件 API 失败时显示 toast", async ({ page }) => {
    // Mock list endpoint for initial page load
    await page.route("**/api/incidents", async (route) => {
      const method = route.request().method();
      if (method === "GET") {
        await route.fulfill({ json: [] });
      } else if (method === "POST") {
        await route.fulfill({
          status: 500,
          json: { detail: "Internal Server Error" },
        });
      } else {
        await route.continue();
      }
    });

    await page.goto("/incidents");
    await page.click('[data-testid="create-incident-btn"]');
    await page.fill('[data-testid="prompt-textarea"]', "Test description");
    await page.click('[data-testid="submit-incident"]');

    // Sonner toast should show error
    await expect(page.getByText("Internal Server Error")).toBeVisible();
  });
});
