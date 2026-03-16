import type { Page } from "@playwright/test";

/** Type text character by character with random 50-150ms delays */
export async function humanType(page: Page, selector: string, text: string) {
  const el = page.locator(selector);
  await el.click();
  for (const char of text) {
    await el.pressSequentially(char, {
      delay: 50 + Math.random() * 100,
    });
  }
}

/** Simulate a 1-3s reading pause */
export async function readingPause() {
  await new Promise((r) => setTimeout(r, 1000 + Math.random() * 2000));
}

/** Simulate a 0.5-1.5s thinking pause */
export async function thinkingPause() {
  await new Promise((r) => setTimeout(r, 500 + Math.random() * 1000));
}

/** Poll backend /health until available (max 30s) */
export async function waitForBackend(baseURL: string) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseURL}/health`);
      if (res.ok) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("Backend did not become available within 30s");
}

/** Delete all connections via API */
export async function cleanupTestData(baseURL: string) {
  try {
    const res = await fetch(`${baseURL}/api/connections`);
    if (!res.ok) return;
    const conns = (await res.json()) as { id: string }[];
    for (const conn of conns) {
      await fetch(`${baseURL}/api/connections/${conn.id}`, {
        method: "DELETE",
      });
    }
  } catch {
    // ignore cleanup errors
  }
}
