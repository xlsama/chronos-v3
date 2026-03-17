import { request } from "@/lib/request";
import type { Skill, SkillDetail } from "@/lib/types";

export function getSkills() {
  return request<Skill[]>("/skills");
}

export function getSkill(slug: string) {
  return request<SkillDetail>(`/skills/${slug}`);
}

export function createSkill(data: {
  slug: string;
  name: string;
  description: string;
  content: string;
}) {
  return request<Skill>("/skills", {
    method: "POST",
    body: data,
  });
}

export function updateSkill(
  slug: string,
  data: {
    name?: string;
    description?: string;
    content?: string;
  },
) {
  return request<Skill>(`/skills/${slug}`, {
    method: "PUT",
    body: data,
  });
}

export function deleteSkill(slug: string) {
  return request(`/skills/${slug}`, { method: "DELETE" });
}
