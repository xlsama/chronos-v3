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

export function updateProjectCloudMd(id: string, cloudMd: string) {
  return request<Project>(`/projects/${id}/cloud-md`, {
    method: "PATCH",
    body: { cloud_md: cloudMd },
  });
}

export function deleteProject(id: string) {
  return request(`/projects/${id}`, { method: "DELETE" });
}
