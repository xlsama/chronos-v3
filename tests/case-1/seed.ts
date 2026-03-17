import type { ApiClient } from "../lib/api-client.js";

export interface SeedData {
  project: { id: string; name: string };
  server: { id: string; name: string };
}

export async function seedCase1(api: ApiClient): Promise<SeedData> {
  console.log("[seed] Seeding case-1 data...");

  const project = await api.createProject({
    name: "E2E Test Project",
    description: "Auto-created for E2E testing",
  });

  const server = await api.createServer({
    name: "test-target",
    host: "localhost",
    port: 12222,
    username: "root",
    password: "testpassword",
  });

  await api.updateProject(project.id, {
    linked_server_ids: [server.id],
  });

  console.log("[seed] Seeding complete");
  return { project, server };
}
