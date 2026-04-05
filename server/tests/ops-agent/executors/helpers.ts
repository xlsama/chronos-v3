import Docker from "dockerode";
import { MongoClient } from "mongodb";
import { SQL } from "bun";
import { db } from "@/db/connection";
import { services } from "@/db/schema";

/**
 * TCP 探活：等待指定端口可连接
 */
export async function waitForPort(
  port: number,
  host = "127.0.0.1",
  timeoutMs = 30_000,
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const socket = Bun.connect({
        hostname: host,
        port,
        socket: {
          data() {},
          open(socket) {
            socket.end();
          },
          error() {},
        },
      });
      await socket;
      return;
    } catch {
      await Bun.sleep(500);
    }
  }
  throw new Error(`waitForPort: ${host}:${port} not ready after ${timeoutMs}ms`);
}

/**
 * 等待 MongoDB 就绪
 */
export async function waitForMongo(uri: string, timeoutMs = 30_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const client = new MongoClient(uri, { serverSelectionTimeoutMS: 2000 });
    try {
      await client.connect();
      await client.db("admin").command({ ping: 1 });
      await client.close();
      return;
    } catch {
      await client.close().catch(() => {});
      await Bun.sleep(1000);
    }
  }
  throw new Error(`waitForMongo: ${uri} not ready after ${timeoutMs}ms`);
}

/**
 * 等待 SQL 数据库就绪（PostgreSQL / MySQL）
 */
export async function waitForSQL(
  config: { hostname: string; port: number; username: string; password: string; database: string },
  timeoutMs = 60_000,
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const sql = new SQL(config);
      await sql.unsafe("SELECT 1");
      await sql.close();
      return;
    } catch {
      await Bun.sleep(1000);
    }
  }
  throw new Error(
    `waitForSQL: ${config.hostname}:${config.port} not ready after ${timeoutMs}ms`,
  );
}

/**
 * 安全删除 Docker 容器（不存在则忽略）
 */
export async function removeContainerIfExists(
  docker: Docker,
  name: string,
): Promise<void> {
  try {
    const container = docker.getContainer(name);
    await container.stop().catch(() => {});
    await container.remove({ force: true }).catch(() => {});
  } catch {
    // container doesn't exist
  }
}

/**
 * 向 chronos DB 插入 service 记录，返回 service id
 */
export async function insertServiceRecord(values: {
  name: string;
  serviceType: string;
  host: string;
  port: number;
  config?: Record<string, unknown>;
}): Promise<string> {
  const [svc] = await db
    .insert(services)
    .values({
      name: values.name,
      serviceType: values.serviceType,
      host: values.host,
      port: values.port,
      config: values.config ?? {},
    })
    .returning();
  return svc.id;
}
