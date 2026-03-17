import { request } from "@/lib/request";
import type { IncidentHistory } from "@/lib/types";

interface IncidentHistoryListResponse {
  items: IncidentHistory[];
  total: number;
  page: number;
  page_size: number;
}

export function getIncidentHistoryList(
  page: number = 1,
  pageSize: number = 20,
  projectId?: string,
  query?: string,
) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (projectId) params.set("project_id", projectId);
  if (query) params.set("query", query);
  return request<IncidentHistoryListResponse>(
    `/incident-history?${params.toString()}`,
  );
}

export function getIncidentHistory(id: string) {
  return request<IncidentHistory>(`/incident-history/${id}`);
}

export function deleteIncidentHistory(id: string) {
  return request<{ ok: boolean }>(`/incident-history/${id}`, {
    method: "DELETE",
  });
}
