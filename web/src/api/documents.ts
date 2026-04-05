import { useAuthStore } from "@/stores/auth";

export function getDocumentFileUrl(documentId: string) {
  return `/api/documents/${documentId}/file`;
}

export async function uploadDocumentFile(
  projectId: string,
  file: File,
) {
  const formData = new FormData();
  formData.append("file", file);

  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`/api/projects/${projectId}/documents/upload`, {
    method: "POST",
    body: formData,
    headers,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}
