import { request } from "@/lib/request";

export function decideApproval(
  id: string,
  data: { decision: string; supplement_text?: string; silent?: boolean },
) {
  const { silent, ...body } = data;
  return request(`/approvals/${id}/decide`, { method: "POST", body, silent });
}
