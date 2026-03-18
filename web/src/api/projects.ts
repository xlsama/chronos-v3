import { request } from "@/lib/request";
import type { PaginatedResponse, Project } from "@/lib/types";

export function getProjects(params?: { page?: number; page_size?: number }) {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size) searchParams.set("page_size", String(params.page_size));
  const qs = searchParams.toString();
  return request<PaginatedResponse<Project>>(
    `/projects${qs ? `?${qs}` : ""}`,
  );
}

export function getProject(id: string) {
  return request<Project>(`/projects/${id}`);
}

export function createProject(data: { name: string; description?: string }) {
  return request<Project>("/projects", { method: "POST", body: data });
}

export function updateProject(
  id: string,
  data: {
    name?: string;
    description?: string;
  },
) {
  return request<Project>(`/projects/${id}`, { method: "PATCH", body: data });
}

export function deleteProject(id: string) {
  return request(`/projects/${id}`, { method: "DELETE" });
}
