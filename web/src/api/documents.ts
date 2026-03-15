import { request } from "@/lib/request";
import type { ProjectDocument } from "@/lib/types";

export function getDocuments(projectId: string) {
  return request<ProjectDocument[]>(`/projects/${projectId}/documents`);
}

export function uploadDocument(
  projectId: string,
  data: { filename: string; content: string; doc_type: string },
) {
  return request<ProjectDocument>(`/projects/${projectId}/documents`, {
    method: "POST",
    body: data,
  });
}

export function deleteDocument(documentId: string) {
  return request(`/documents/${documentId}`, { method: "DELETE" });
}
