import { request } from "@/lib/request";
import type { Incident, Message } from "@/lib/types";

export function getIncidents() {
  return request<Incident[]>("/incidents");
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
  return request(`/incidents/${incidentId}/messages`, {
    method: "POST",
    body: { content, attachment_ids: attachmentIds },
  });
}

export function saveToMemory(incidentId: string) {
  return request<{ ok: boolean; incident_history_id?: string; error?: string }>(
    `/incidents/${incidentId}/save-to-memory`,
    { method: "POST" },
  );
}
