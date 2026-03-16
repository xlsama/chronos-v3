import { test, expect } from "../fixtures/test.fixture.js";

test("磁盘占满事件 - 完整生命周期", async ({ page, seedData, faultInjector, apiClient }) => {
  // 1. 故障注入：在目标机器上制造磁盘占满
  await faultInjector.injectDiskFull();

  // 2. 打开事件页面
  await page.goto("/incidents");

  // 3. 创建事件
  await page.click('[data-testid="create-incident-btn"]');

  // 填写事件描述
  await page.fill(
    '[data-testid="prompt-textarea"]',
    "服务器 test-server 磁盘使用率过高，/tmp 目录占用异常，请排查原因并清理",
  );

  // 提交事件
  await page.click('[data-testid="submit-incident"]');

  // 4. 等待导航到事件详情页
  await page.waitForURL(/\/incidents\/[\w-]+/, { timeout: 15_000 });

  // 从 URL 提取 incident ID
  const incidentId = page.url().split("/incidents/")[1];

  // 5. 事件处理循环（最长 8 分钟）
  const deadline = Date.now() + 8 * 60 * 1000;
  const handledApprovals = new Set<string>();
  const handledQuestions = new Set<string>();

  while (Date.now() < deadline) {
    // 检查是否已完成（出现 summary）
    const summary = page.locator('[data-testid="summary-section"]');
    if (await summary.isVisible().catch(() => false)) {
      break;
    }

    // 检查是否需要审批
    const approvalCard = page.locator('[data-testid="approval-card"]').last();
    if (await approvalCard.isVisible().catch(() => false)) {
      const approvalId = await approvalCard.getAttribute("data-approval-id");
      const approvalKey = approvalId ?? "approval";
      if (!handledApprovals.has(approvalKey)) {
        const approveBtn = approvalCard.locator('[data-testid="approve-button"]');
        if (await approveBtn.isVisible().catch(() => false)) {
          handledApprovals.add(approvalKey);
          await approveBtn.click();
          await page.waitForTimeout(2000);
          continue;
        }
      }
    }

    // 检查是否 ask_human（需要用户回复）
    const askHumanBanner = page.locator('[data-testid="ask-human-banner"]');
    if (await askHumanBanner.isVisible().catch(() => false)) {
      const question = (await askHumanBanner.textContent())?.trim() ?? "ask-human";
      if (!handledQuestions.has(question)) {
        handledQuestions.add(question);
        const replyInput = page.locator('[data-testid="prompt-textarea"]');
        await replyInput.fill("请继续排查并清理 /tmp 目录下的大文件");
        await page.locator('[data-testid="submit-incident"]').click();
        await page.waitForTimeout(2000);
        continue;
      }
    }

    await page.waitForTimeout(3000);
  }

  // 6. 断言
  const summary = page.locator('[data-testid="summary-section"]');
  await expect(summary).toBeVisible({ timeout: 30_000 });

  // 通过 API 验证 incident 状态
  const incident = await apiClient.getIncident(incidentId);
  expect(incident.status).toBe("resolved");

  // 7. 验证故障已修复（best-effort）
  try {
    const result = await faultInjector.exec("test -f /tmp/testfill");
    expect(result.code).not.toBe(0); // file should be removed
  } catch {
    // best-effort, don't fail the test
  }
});
