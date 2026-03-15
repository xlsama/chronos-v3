import { ofetch } from "ofetch";
import type { Attachment } from "@/lib/types";

export function uploadFiles(files: File[]): Promise<Attachment[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  return ofetch<Attachment[]>("/api/attachments", {
    method: "POST",
    body: formData,
  });
}

export function getAttachmentUrl(id: string): string {
  return `/api/attachments/${id}/download`;
}
