import { request } from "@/lib/request";
import type { Project } from "@/lib/types";

export function getProjects() {
  return request<Project[]>("/projects");
}

export function getProject(id: string) {
  return request<Project>(`/projects/${id}`);
}

export function createProject(data: { name: string; description?: string }) {
  return request<Project>("/projects", { method: "POST", body: data });
}

export function updateProjectServiceMd(id: string, serviceMd: string) {
  return request<Project>(`/projects/${id}/service-md`, {
    method: "PATCH",
    body: { service_md: serviceMd },
  });
}

export function deleteProject(id: string) {
  return request(`/projects/${id}`, { method: "DELETE" });
}
