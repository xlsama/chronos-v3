import type { ApiClient } from "../lib/api-client.js";

export interface SeedDataCase2 {
  project: { id: string; name: string };
  appServer: { id: string; name: string };
  dataServer: { id: string; name: string };
}

export async function seedCase2(api: ApiClient): Promise<SeedDataCase2> {
  console.log("[seed] Seeding case-2 data...");

  const project = await api.createProject({
    name: "微服务订单系统",
    description: "订单系统依赖库存服务的微服务架构，用于 E2E 链路故障测试",
  });

  const appServer = await api.createServer({
    name: "app-server",
    host: "localhost",
    port: 12223,
    username: "root",
    password: "testpassword",
  });

  const dataServer = await api.createServer({
    name: "data-server",
    host: "localhost",
    port: 12224,
    username: "root",
    password: "testpassword",
  });

  await api.updateProject(project.id, {
    linked_server_ids: [appServer.id, dataServer.id],
  });

  console.log("[seed] Seeding case-2 complete");
  return { project, appServer, dataServer };
}
