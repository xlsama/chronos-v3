import { createBaseFixture, expect } from "../lib/base-fixture.js";
import { seedCase1, type SeedData } from "./seed.js";
import { FaultInjector } from "../lib/ssh.js";

export const test = createBaseFixture("case-1").extend<{
  seedData: SeedData;
  faultInjector: FaultInjector;
}>({
  seedData: async ({ apiClient }, use) => {
    await use(await seedCase1(apiClient));
  },

  faultInjector: async ({}, use) => {
    await use(new FaultInjector());
  },
});

export { expect };
