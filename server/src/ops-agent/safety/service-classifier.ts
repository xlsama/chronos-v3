import type { CommandType } from "../types";

// ─── 静态 operation 分类映射 ───────────────────────────

const OPERATION_MAP: Record<string, Record<string, CommandType>> = {
  docker: {
    // Read
    listContainers: "read",
    inspectContainer: "read",
    containerLogs: "read",
    containerTop: "read",
    containerStats: "read",
    listImages: "read",
    listNetworks: "read",
    listVolumes: "read",
    systemInfo: "read",
    systemDf: "read",
    // Write
    startContainer: "write",
    stopContainer: "write",
    restartContainer: "write",
    pauseContainer: "write",
    unpauseContainer: "write",
    pullImage: "write",
    // Dangerous
    removeContainer: "dangerous",
    removeImage: "dangerous",
    killContainer: "dangerous",
  },

  kubernetes: {
    // Read
    listNamespaces: "read",
    listPods: "read",
    describePod: "read",
    getPodLogs: "read",
    listDeployments: "read",
    describeDeployment: "read",
    listServices: "read",
    listNodes: "read",
    // Write
    scaleDeployment: "write",
    restartDeployment: "write",
    // Dangerous
    deletePod: "dangerous",
  },

  mongodb: {
    // Read
    listDatabases: "read",
    listCollections: "read",
    findDocuments: "read",
    countDocuments: "read",
    aggregate: "read",
    // Write
    insertOne: "write",
    updateMany: "write",
    // Dangerous
    deleteMany: "dangerous",
  },

  postgresql: {
    listDatabases: "read",
    listTables: "read",
    describeTable: "read",
    tableRowCount: "read",
    // executeSql 走 classifySql()
  },

  mysql: {
    listDatabases: "read",
    listTables: "read",
    describeTable: "read",
    tableRowCount: "read",
    // executeSql 走 classifySql()
  },
};

// ─── SQL 内容分类 ─────────────────────────────────────

const SQL_BLOCKED_RE = /\b(DROP\s+DATABASE|TRUNCATE\s+TABLE|DROP\s+SCHEMA)\b/i;
const SQL_DANGEROUS_RE = /\b(DELETE\s+FROM|DROP\s+TABLE|DROP\s+INDEX|ALTER\s+TABLE\s+\S+\s+DROP)\b/i;
const SQL_WRITE_RE = /\b(INSERT|UPDATE|CREATE|ALTER|GRANT|REVOKE|REPLACE)\b/i;
const SQL_READ_RE = /^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN|WITH)\b/i;

function classifySql(params?: Record<string, unknown>): CommandType {
  const query = ((params?.query as string) || "").trim();
  if (!query) return "read"; // 空 query 在 executor 层会报错

  if (SQL_BLOCKED_RE.test(query)) return "blocked";
  if (SQL_DANGEROUS_RE.test(query)) return "dangerous";
  if (SQL_WRITE_RE.test(query)) return "write";
  if (SQL_READ_RE.test(query)) return "read";
  return "write"; // fail-closed
}

// ─── 主分类函数 ───────────────────────────────────────

export function classifyServiceOperation(
  serviceType: string,
  operation: string,
  params?: Record<string, unknown>,
): CommandType {
  const typeMap = OPERATION_MAP[serviceType];
  if (!typeMap) return "write"; // 未知 service type → fail-closed

  // executeSql 特殊处理：需要检查 SQL 内容
  if (operation === "executeSql" && (serviceType === "postgresql" || serviceType === "mysql")) {
    return classifySql(params);
  }

  const commandType = typeMap[operation];
  if (!commandType) return "write"; // 未知 operation → fail-closed

  return commandType;
}
