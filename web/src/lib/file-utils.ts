import type { FileType } from "@/components/ui/file-preview";

export function getFileTypeFromContentType(contentType: string, filename: string): FileType {
  if (contentType.startsWith("image/")) return "image";
  if (contentType === "application/pdf") return "pdf";
  if (contentType === "text/markdown" || filename.endsWith(".md")) return "markdown";
  if (contentType === "text/csv" || filename.endsWith(".csv")) return "csv";
  if (contentType.includes("json")) return "json";
  if (contentType.includes("yaml") || contentType.includes("yml")) return "yaml";
  if (contentType.includes("html")) return "html";
  if (filename.endsWith(".log")) return "log";
  return "text";
}

export function isImageType(contentType: string): boolean {
  return contentType.startsWith("image/");
}
