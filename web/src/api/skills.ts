import { request } from "@/lib/request";
import type { Skill, SkillDetail } from "@/lib/types";

export function getSkills() {
  return request<Skill[]>("/skills");
}

export function getSkill(slug: string) {
  return request<SkillDetail>(`/skills/${slug}`);
}

export function createSkill(data: { slug: string }) {
  return request<Skill>("/skills", {
    method: "POST",
    body: data,
  });
}

export function updateSkill(slug: string, data: { content: string }) {
  return request<Skill>(`/skills/${slug}`, {
    method: "PUT",
    body: data,
  });
}

export function deleteSkill(slug: string) {
  return request(`/skills/${slug}`, { method: "DELETE" });
}

// ── File Management ─────────────────────────────────────────

export function getSkillFile(slug: string, path: string) {
  return request<{ content: string }>(`/skills/${slug}/files/${path}`);
}

export function putSkillFile(slug: string, path: string, content: string) {
  return request(`/skills/${slug}/files/${path}`, {
    method: "PUT",
    body: { content },
  });
}

export function deleteSkillFile(slug: string, path: string) {
  return request(`/skills/${slug}/files/${path}`, { method: "DELETE" });
}
