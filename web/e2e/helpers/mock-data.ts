import type {
  Incident,
  ApprovalRequest,
  Connection,
  Service,
} from "../../src/lib/types";

export const INCIDENT_ID = "inc-test-001";
export const APPROVAL_ID = "approval-001";
export const APPROVAL_ID_OOM = "approval-oom-001";

export function createMockIncident(
  overrides?: Partial<Incident>,
): Incident {
  return {
    id: INCIDENT_ID,
    title: "Nginx 服务异常",
    description: "生产环境 502 错误",
    status: "investigating",
    severity: "high",
    connection_id: "infra-001",
    project_id: "proj-001",
    summary_md: null,
    thread_id: "thread-001",
    saved_to_memory: false,
    created_at: "2026-03-16T10:00:00Z",
    updated_at: "2026-03-16T10:00:00Z",
    ...overrides,
  };
}

export function createMockIncidentList(): Incident[] {
  return [
    createMockIncident(),
    createMockIncident({
      id: "inc-test-002",
      title: "数据库连接超时",
      description: "PostgreSQL 连接池耗尽",
      severity: "critical",
      status: "open",
      created_at: "2026-03-16T09:00:00Z",
      updated_at: "2026-03-16T09:00:00Z",
    }),
  ];
}

// ── Connection & Service ──

export const CONN_SSH_ID = "infra-ssh-001";
export const CONN_K8S_ID = "infra-k8s-002";

export function createMockConnection(
  overrides?: Partial<Connection>,
): Connection {
  return {
    id: CONN_SSH_ID,
    name: "Production Server",
    type: "ssh",
    host: "192.168.1.10",
    port: 22,
    username: "root",
    status: "online",
    project_id: null,
    created_at: "2026-03-16T08:00:00Z",
    updated_at: "2026-03-16T08:00:00Z",
    ...overrides,
  };
}

export function createMockK8sConnection(
  overrides?: Partial<Connection>,
): Connection {
  return {
    id: CONN_K8S_ID,
    name: "K8s Production",
    type: "kubernetes",
    host: "",
    port: 0,
    username: "",
    status: "online",
    project_id: null,
    created_at: "2026-03-16T09:00:00Z",
    updated_at: "2026-03-16T09:00:00Z",
    ...overrides,
  };
}

export function createMockConnectionList(): Connection[] {
  return [createMockConnection(), createMockK8sConnection()];
}

export function createMockService(overrides?: Partial<Service>): Service {
  return {
    id: "svc-001",
    connection_id: CONN_SSH_ID,
    name: "nginx",
    port: 80,
    namespace: null,
    status: "unknown",
    discovery_method: "auto_discovered",
    created_at: "2026-03-16T10:00:00Z",
    updated_at: "2026-03-16T10:00:00Z",
    ...overrides,
  };
}

export function createMockServiceList(): Service[] {
  return [
    createMockService(),
    createMockService({
      id: "svc-002",
      name: "redis",
      port: 6379,
    }),
    createMockService({
      id: "svc-003",
      name: "postgres",
      port: 5432,
    }),
  ];
}

// ── Approval ──

export function createMockApprovalDecision(
  overrides?: Partial<ApprovalRequest>,
): ApprovalRequest {
  return {
    id: APPROVAL_ID,
    incident_id: INCIDENT_ID,
    tool_name: "exec_write_tool",
    tool_args: JSON.stringify({ command: "systemctl restart nginx" }),
    decision: "approved",
    decided_by: "admin",
    decided_at: "2026-03-16T10:05:00Z",
    created_at: "2026-03-16T10:03:00Z",
    ...overrides,
  };
}
