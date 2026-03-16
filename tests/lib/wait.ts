export async function waitForHealth(
  url: string,
  timeoutMs: number = 60_000,
): Promise<void> {
  const start = Date.now();
  let delay = 500;

  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.5, 5000);
  }

  throw new Error(`Health check timeout: ${url} not ready after ${timeoutMs}ms`);
}
