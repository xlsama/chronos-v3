import type { Incident, ApprovalRequest } from "../../src/lib/types";

export const INCIDENT_ID = "inc-test-001";
export const APPROVAL_ID = "approval-001";

export function createMockIncident(
  overrides?: Partial<Incident>,
): Incident {
  return {
    id: INCIDENT_ID,
    title: "Nginx 服务异常",
    description: "生产环境 502 错误",
    status: "investigating",
    severity: "high",
    infrastructure_id: "infra-001",
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
