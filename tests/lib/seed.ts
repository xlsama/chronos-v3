import type { ApiClient } from "./api-client.js";

export interface SeedData {
  project: { id: string; name: string };
  connection: { id: string };
  service: { id: string; name: string };
}

export async function seedCase1(api: ApiClient): Promise<SeedData> {
  console.log("[seed] Seeding case-1 data...");

  const project = await api.createProject({
    name: "E2E Test Project",
    description: "Auto-created for E2E testing",
  });

  const connection = await api.createConnection({
    name: "test-target",
    host: "localhost",
    port: 12222,
    username: "root",
    password: "testpassword",
    project_id: project.id,
  });

  const service = await api.createService({
    name: "test-server",
    service_type: "system_service",
    project_id: project.id,
  });

  await api.createBinding({
    service_id: service.id,
    connection_id: connection.id,
    project_id: project.id,
  });

  console.log("[seed] Seeding complete");
  return { project, connection, service };
}
