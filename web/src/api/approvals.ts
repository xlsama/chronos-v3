import { request } from "@/lib/request";
import type { ApprovalRequest } from "@/lib/types";

export function getApproval(id: string) {
  return request<ApprovalRequest>(`/approvals/${id}`);
}

export function decideApproval(
  id: string,
  data: { decision: string; decided_by: string },
) {
  return request(`/approvals/${id}/decide`, { method: "POST", body: data });
}
