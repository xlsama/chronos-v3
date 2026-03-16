import type { Page } from "@playwright/test";

export interface IncidentLoopOptions {
  /** 最长等待时间（毫秒），默认 8 分钟 */
  timeoutMs?: number;
  /** ask_human 时的自动回复文本 */
  askHumanReply: string;
}

export async function waitForIncidentResolution(
  page: Page,
  options: IncidentLoopOptions,
): Promise<void> {
  const { timeoutMs = 8 * 60 * 1000, askHumanReply } = options;
  const deadline = Date.now() + timeoutMs;
  const handledApprovals = new Set<string>();
  const handledQuestions = new Set<string>();

  while (Date.now() < deadline) {
    const summary = page.locator('[data-testid="summary-section"]');
    if (await summary.isVisible().catch(() => false)) break;

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

    const askHumanBanner = page.locator('[data-testid="ask-human-banner"]');
    if (await askHumanBanner.isVisible().catch(() => false)) {
      const question = (await askHumanBanner.textContent())?.trim() ?? "ask-human";
      if (!handledQuestions.has(question)) {
        handledQuestions.add(question);
        await page.locator('[data-testid="prompt-textarea"]').fill(askHumanReply);
        await page.locator('[data-testid="submit-incident"]').click();
        await page.waitForTimeout(2000);
        continue;
      }
    }

    await page.waitForTimeout(3000);
  }
}
