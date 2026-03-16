import { test as base } from "@playwright/test";
import { TestInfra } from "./docker.js";
import { ProcessManager } from "./processes.js";
import { ApiClient } from "./api-client.js";
import { waitForHealth } from "./wait.js";

export interface BaseFixtures {
  apiClient: ApiClient;
}

export interface BaseWorkerFixtures {
  infra: void;
}

export function createBaseFixture(caseName: string) {
  return base.extend<BaseFixtures, BaseWorkerFixtures>({
    infra: [
      async ({}, use) => {
        const infra = new TestInfra(caseName);
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
  });
}

export { expect } from "@playwright/test";
