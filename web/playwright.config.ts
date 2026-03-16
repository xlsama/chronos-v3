import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://localhost:5173",
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  retries: 1,
  projects: [
    {
      name: "mock",
      testMatch: /^(?!.*real-e2e).*\.spec\.ts$/,
      use: {
        baseURL: "http://localhost:5173",
        screenshot: "only-on-failure",
        trace: "on-first-retry",
      },
    },
    {
      name: "real-e2e",
      testDir: "./e2e/real-e2e",
      timeout: 180_000,
      expect: { timeout: 120_000 },
      retries: 0,
      use: {
        baseURL: "http://localhost:5173",
        screenshot: "only-on-failure",
        trace: "on",
        video: "on",
      },
    },
  ],
  webServer: [
    {
      command: "pnpm dev",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
