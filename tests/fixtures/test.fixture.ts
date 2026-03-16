import { test as base } from "@playwright/test";
import { TestInfra } from "../lib/docker.js";
import { ProcessManager } from "../lib/processes.js";
import { ApiClient } from "../lib/api-client.js";
import { seedCase1, type SeedData } from "../lib/seed.js";
import { FaultInjector } from "../lib/ssh.js";
import { waitForHealth } from "../lib/wait.js";

interface TestFixtures {
  apiClient: ApiClient;
  seedData: SeedData;
  faultInjector: FaultInjector;
}

interface WorkerFixtures {
  infra: void;
}

export const test = base.extend<TestFixtures, WorkerFixtures>({
  // Worker-scoped: start infra + processes once per worker
  infra: [
    async ({}, use) => {
      const infra = new TestInfra("case-1");
      const proc = new ProcessManager();

      infra.start();

      proc.runMigrations();
      proc.startBackend();
      await waitForHealth("http://localhost:8000/api/projects", 30_000);
      proc.startFrontend();
      await waitForHealth("http://localhost:5173", 30_000);

      await use();

      proc.stopAll();
      infra.stop();
    },
    { scope: "worker", auto: true },
  ],

  apiClient: async ({}, use) => {
    await use(new ApiClient());
  },

  seedData: async ({ apiClient }, use) => {
    const data = await seedCase1(apiClient);
    await use(data);
  },

  faultInjector: async ({}, use) => {
    await use(new FaultInjector());
  },
});

export { expect } from "@playwright/test";
