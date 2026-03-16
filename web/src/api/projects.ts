import { request } from "@/lib/request";
import type { Project, ProjectTopology } from "@/lib/types";

export function getProjects() {
  return request<Project[]>("/projects");
}

export function getProject(id: string) {
  return request<Project>(`/projects/${id}`);
}

export function createProject(data: { name: string; description?: string }) {
  return request<Project>("/projects", { method: "POST", body: data });
}

export function getProjectTopology(id: string) {
  return request<ProjectTopology>(`/projects/${id}/topology`);
}

export function deleteProject(id: string) {
  return request(`/projects/${id}`, { method: "DELETE" });
}
