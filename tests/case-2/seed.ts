import type { ApiClient } from "../lib/api-client.js";

export interface SeedDataCase2 {
  project: { id: string; name: string };
  appServerConnection: { id: string };
  dataServerConnection: { id: string };
  orderApi: { id: string; name: string };
  inventoryApi: { id: string; name: string };
  inventoryPostgres: { id: string; name: string };
}

export async function seedCase2(api: ApiClient): Promise<SeedDataCase2> {
  console.log("[seed] Seeding case-2 data...");

  const project = await api.createProject({
    name: "微服务订单系统",
    description: "订单系统依赖库存服务的微服务架构，用于 E2E 链路故障测试",
  });

  // 2 SSH connections
  const appServerConnection = await api.createConnection({
    name: "app-server",
    host: "localhost",
    port: 12223,
    username: "root",
    password: "testpassword",
    project_id: project.id,
  });

  const dataServerConnection = await api.createConnection({
    name: "data-server",
    host: "localhost",
    port: 12224,
    username: "root",
    password: "testpassword",
    project_id: project.id,
  });

  // 3 services
  const orderApi = await api.createService({
    name: "order-api",
    service_type: "backend_api",
    project_id: project.id,
    description: "订单服务，基于 Flask + SQLite，通过 Nginx 反向代理对外提供 HTTP 接口",
    keywords: ["flask", "nginx", "order", "sqlite"],
  });

  const inventoryApi = await api.createService({
    name: "inventory-api",
    service_type: "backend_api",
    project_id: project.id,
    description: "库存服务，基于 Flask + PostgreSQL，提供商品库存查询接口",
    keywords: ["flask", "inventory", "postgresql"],
  });

  const inventoryPostgres = await api.createService({
    name: "inventory-postgres",
    service_type: "database",
    project_id: project.id,
    description: "库存数据库，PostgreSQL，包含 products 和 stock 表",
    keywords: ["postgresql", "database"],
  });

  // 3 bindings: each service to its connection
  await api.createBinding({
    service_id: orderApi.id,
    connection_id: appServerConnection.id,
    project_id: project.id,
  });

  await api.createBinding({
    service_id: inventoryApi.id,
    connection_id: dataServerConnection.id,
    project_id: project.id,
  });

  await api.createBinding({
    service_id: inventoryPostgres.id,
    connection_id: dataServerConnection.id,
    project_id: project.id,
  });

  // 2 dependencies
  await api.createDependency({
    project_id: project.id,
    from_service_id: orderApi.id,
    to_service_id: inventoryApi.id,
    dependency_type: "api_call",
    description: "order-api 调用 inventory-api 的 /api/inventory/{product_id} 接口查询库存",
  });

  await api.createDependency({
    project_id: project.id,
    from_service_id: inventoryApi.id,
    to_service_id: inventoryPostgres.id,
    dependency_type: "data_flow",
    description: "inventory-api 查询 PostgreSQL inventory 数据库获取商品和库存数据",
  });

  console.log("[seed] Seeding case-2 complete");
  return {
    project,
    appServerConnection,
    dataServerConnection,
    orderApi,
    inventoryApi,
    inventoryPostgres,
  };
}
