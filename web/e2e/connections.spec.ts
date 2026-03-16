import { test, expect } from "./fixtures/mock-api";
import { CONN_SSH_ID, CONN_K8S_ID } from "./helpers/mock-data";

test.describe("Connections 页面", () => {
  test("显示基础设施列表", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await page.goto("/connections");

    await expect(page.getByText("Production Server")).toBeVisible();
    await expect(page.getByText("K8s Production")).toBeVisible();

    // Type badges
    const badges = page.getByTestId("conn-type-badge");
    await expect(badges.nth(0)).toContainText("SSH");
    await expect(badges.nth(1)).toContainText("K8s");
  });

  test("空列表显示提示", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes([]);
    await page.goto("/connections");

    await expect(page.getByText("No connections configured")).toBeVisible();
  });

  test("创建 SSH 基础设施", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await page.goto("/connections");

    // Open dialog
    await page.getByRole("button", { name: "Add Connection" }).click();
    await expect(
      page.getByRole("heading", { name: "Add Connection" }),
    ).toBeVisible();

    // Fill SSH form (SSH is default type)
    await page.getByPlaceholder("e.g. Production Server").fill("New Server");
    await page.getByPlaceholder("e.g. 192.168.1.1").fill("10.0.0.1");

    // Submit
    await page.getByRole("button", { name: "Add", exact: true }).click();

    // Verify toast
    await expect(page.getByText("Connection added")).toBeVisible();
  });

  test("创建 K8s 基础设施", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await page.goto("/connections");

    // Open dialog
    await page.getByRole("button", { name: "Add Connection" }).click();

    // Switch to Kubernetes type
    await page.getByRole("combobox").click();
    await page.getByRole("option", { name: "Kubernetes Cluster" }).click();

    // Fill K8s form
    await page.getByPlaceholder("e.g. K8s Production").fill("Staging Cluster");
    await page
      .getByPlaceholder("Paste kubeconfig YAML content here...")
      .fill("apiVersion: v1\nclusters: []");

    // Submit
    await page.getByRole("button", { name: "Add", exact: true }).click();

    await expect(page.getByText("Connection added")).toBeVisible();
  });

  test("测试连接", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await page.goto("/connections");

    await expect(page.getByText("Production Server")).toBeVisible();

    // Click test button on SSH connection
    await page.getByTestId(`conn-test-${CONN_SSH_ID}`).click();

    await expect(page.getByText("Connection test completed")).toBeVisible();
  });

  test("删除基础设施", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await page.goto("/connections");

    await expect(page.getByText("Production Server")).toBeVisible();

    // Click delete button
    await page.getByTestId(`conn-delete-${CONN_SSH_ID}`).click();

    await expect(page.getByText("Connection deleted")).toBeVisible();
  });

  test("展开显示服务列表", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await mockApi.setupServiceRoutes();
    await page.goto("/connections");

    await expect(page.getByText("Production Server")).toBeVisible();

    // Expand SSH connection
    await page.getByTestId(`conn-expand-${CONN_SSH_ID}`).click();

    // Wait for services to load
    await expect(page.getByText("nginx")).toBeVisible();
    await expect(page.getByText("redis")).toBeVisible();
    await expect(page.getByText("postgres")).toBeVisible();
  });

  test("手动添加服务", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await mockApi.setupServiceRoutes();
    await page.goto("/connections");

    // Expand connection
    await page.getByTestId(`conn-expand-${CONN_SSH_ID}`).click();
    await expect(page.getByText("Services", { exact: true })).toBeVisible();

    // Click Add button
    await page.getByTestId("add-service-btn").first().click();
    await expect(
      page.getByRole("heading", { name: "Add Service" }),
    ).toBeVisible();

    // Fill form
    await page.getByPlaceholder("e.g. mysql-main").fill("my-app");

    // Submit
    await page.getByRole("button", { name: "Add", exact: true }).click();

    await expect(page.getByText("Service added")).toBeVisible();
  });

  test("自动发现服务", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await mockApi.setupServiceRoutes();
    await mockApi.setupDiscoverServices();
    await page.goto("/connections");

    // Expand connection
    await page.getByTestId(`conn-expand-${CONN_SSH_ID}`).click();
    await expect(page.getByText("Services", { exact: true })).toBeVisible();

    // Click Discover button
    await page.getByTestId("discover-services-btn").first().click();
    await expect(
      page.getByRole("heading", { name: "Auto-discover Services" }),
    ).toBeVisible();

    // Start discovery
    await page.getByRole("button", { name: "Start Discovery" }).click();

    await expect(page.getByText("Discovered 3 services")).toBeVisible();
  });

  test("空服务列表提示", async ({ page, mockApi }) => {
    await mockApi.setupConnectionRoutes();
    await mockApi.setupServiceRoutes(CONN_SSH_ID, []);
    await page.goto("/connections");

    // Expand connection
    await page.getByTestId(`conn-expand-${CONN_SSH_ID}`).click();

    await expect(page.getByText("No services discovered")).toBeVisible();
  });
});
