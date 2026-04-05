import { z } from "zod";
import { eq } from "drizzle-orm";
import type { ToolDefinition, PermissionResult } from "../types";
import { executeService } from "../executors/registry";
import { classifyServiceOperation } from "../safety/service-classifier";
import { toPermissionResult } from "../safety/permissions";
import { db } from "../../db/connection";
import { services } from "../../db/schema";

const schema = z.object({
  serviceId: z.string().describe("预注册的 Service ID"),
  operation: z
    .string()
    .describe(
      "操作名称，例如: listContainers, inspectContainer, containerLogs, listPods, getPodLogs, executeSql, findDocuments 等",
    ),
  parameters: z
    .record(z.string(), z.any())
    .optional()
    .default({})
    .describe("操作的具体参数（JSON 对象）"),
});

type ServiceExecArgs = z.infer<typeof schema>;

export const serviceExecTool: ToolDefinition<ServiceExecArgs> = {
  name: "service_exec",
  description: `执行预注册的 Service 操作。支持 Docker、Kubernetes、MySQL、PostgreSQL、MongoDB 等。
所有操作通过结构化的 operation + parameters 执行，绝不要输出 shell 命令字符串。

使用前先调用 list_services 查看可用的 Service ID。`,
  parameters: schema,
  needsPermissionCheck: true,
  maxResultChars: 30_000,

  async checkPermission(args): Promise<PermissionResult> {
    const [service] = await db
      .select({ serviceType: services.serviceType })
      .from(services)
      .where(eq(services.id, args.serviceId))
      .limit(1);

    const serviceType = service?.serviceType ?? "unknown";
    const commandType = classifyServiceOperation(serviceType, args.operation, args.parameters);
    return toPermissionResult(commandType, `Service 操作: ${args.operation}`);
  },

  async execute(args) {
    return executeService(args.serviceId, args.operation, args.parameters);
  },
};
