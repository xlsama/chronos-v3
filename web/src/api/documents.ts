import { request } from "@/lib/request";
import type { ProjectDocument, ProjectDocumentDetail } from "@/lib/types";

export function getDocuments(projectId: string) {
  return request<ProjectDocument[]>(`/projects/${projectId}/documents`);
}

export function getDocument(documentId: string) {
  return request<ProjectDocumentDetail>(`/documents/${documentId}`);
}

export function updateDocument(documentId: string, content: string) {
  return request<ProjectDocumentDetail>(`/documents/${documentId}`, {
    method: "PUT",
    body: { content },
  });
}

export function getDocumentFileUrl(documentId: string) {
  return `/api/documents/${documentId}/file`;
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

export async function uploadDocumentFile(
  projectId: string,
  file: File,
): Promise<ProjectDocument> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`/api/projects/${projectId}/documents/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export function deleteDocument(documentId: string) {
  return request(`/documents/${documentId}`, { method: "DELETE" });
}
