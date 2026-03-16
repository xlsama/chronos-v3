import { createBaseFixture, expect } from "../lib/base-fixture.js";
import { seedCase2, type SeedDataCase2 } from "./seed.js";
import { FaultInjector } from "../lib/ssh.js";

export const test = createBaseFixture("case-2").extend<{
  seedData: SeedDataCase2;
  appServerInjector: FaultInjector;
  dataServerInjector: FaultInjector;
}>({
  seedData: async ({ apiClient }, use) => {
    await use(await seedCase2(apiClient));
  },

  appServerInjector: async ({}, use) => {
    await use(new FaultInjector({ port: 12223 }));
  },

  dataServerInjector: async ({}, use) => {
    await use(new FaultInjector({ port: 12224 }));
  },
});

export { expect };
