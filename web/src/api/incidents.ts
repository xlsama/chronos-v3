import { request } from "@/lib/request";
import type { Incident, Message, PaginatedResponse, SSEEvent } from "@/lib/types";

export function getIncidents(params?: {
  status?: string;
  page?: number;
  page_size?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  const qs = searchParams.toString();
  return request<PaginatedResponse<Incident>>(
    `/incidents${qs ? `?${qs}` : ""}`,
  );
}

export function getIncident(id: string) {
  return request<Incident>(`/incidents/${id}`);
}

export function createIncident(data: {
  description: string;
  attachment_ids?: string[];
}) {
  return request<Incident>("/incidents", { method: "POST", body: data });
}

export function getIncidentMessages(incidentId: string) {
  return request<Message[]>(`/incidents/${incidentId}/messages`);
}

export function sendIncidentMessage(
  incidentId: string,
  content: string,
  attachmentIds?: string[],
) {
  return request<Message>(`/incidents/${incidentId}/messages`, {
    method: "POST",
    body: { content, attachment_ids: attachmentIds },
  });
}

export function getIncidentEvents(incidentId: string) {
  return request<SSEEvent[]>(`/incidents/${incidentId}/events`);
}

export function stopIncident(incidentId: string) {
  return request<Incident>(`/incidents/${incidentId}/stop`, {
    method: "POST",
  });
}
