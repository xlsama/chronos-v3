import { test, expect } from "./fixtures/mock-api";

test.describe("事件列表页", () => {
  test("显示事件列表", async ({ page, mockApi }) => {
    await mockApi.setupIncidentRoutes();
    await page.goto("/incidents");

    await expect(page.getByText("Nginx 服务异常")).toBeVisible();
    await expect(page.getByText("数据库连接超时")).toBeVisible();
  });

  test("空列表显示提示", async ({ page, mockApi }) => {
    await mockApi.setupIncidentRoutes([]);
    await page.goto("/incidents");

    await expect(page.getByText("No incidents yet")).toBeVisible();
  });

  test("点击事件跳转到详情页", async ({ page, mockApi }) => {
    await mockApi.setupAll();
    await page.goto("/incidents");

    await page.getByText("Nginx 服务异常").click();
    await page.waitForURL(/\/incidents\/inc-test-001/);
  });
});
