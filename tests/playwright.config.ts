import { defineConfig } from "@playwright/test";

export default defineConfig({
  testMatch: "case-*/**/*.spec.ts",
  timeout: 10 * 60 * 1000,
  expect: {
    timeout: 5 * 60 * 1000,
  },
  workers: 1,
  retries: 0,
  use: {
    baseURL: "http://localhost:5173",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  outputDir: "test-results",
});
