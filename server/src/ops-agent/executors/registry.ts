import { destr } from "destr";
import { db } from "../../db/connection";
import { services } from "../../db/schema";
import { eq } from "drizzle-orm";
import type { Executor } from "../types";
import { dockerExecutor } from "./docker";
import { k8sExecutor } from "./kubernetes";
import { sqlExecutor } from "./sql";
import { mysqlExecutor } from "./mysql";
import { mongoExecutor } from "./mongodb";

const executors: Record<string, Executor> = {
  docker: dockerExecutor,
  kubernetes: k8sExecutor,
  mysql: mysqlExecutor,
  postgresql: sqlExecutor,
  mongodb: mongoExecutor,
};

export async function executeService(
  serviceId: string,
  operation: string,
  rawParams: Record<string, unknown> | string = {},
): Promise<unknown> {
  // LLM 可能把 parameters 返回为 JSON 字符串而不是对象，用 destr 安全解析
  const params: Record<string, unknown> =
    typeof rawParams === "string" ? (destr(rawParams) as Record<string, unknown>) ?? {} : rawParams;
  const [service] = await db
    .select()
    .from(services)
    .where(eq(services.id, serviceId))
    .limit(1);

  if (!service) {
    throw new Error(`Service not found: ${serviceId}`);
  }

  const executor = executors[service.serviceType];
  if (!executor) {
    throw new Error(
      `Unsupported service type: ${service.serviceType}. Supported: ${Object.keys(executors).join(", ")}`,
    );
  }

  const connectionInfo: Record<string, unknown> = {
    host: service.host,
    port: service.port,
    ...(typeof service.config === "object" && service.config !== null
      ? (service.config as Record<string, unknown>)
      : {}),
  };

  return executor(connectionInfo, operation, params);
}
