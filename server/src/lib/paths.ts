import { join } from "path";
import { env } from "@/env";

export const dataDir = () => env.DATA_DIR;
export const seedsDir = () => env.SEEDS_DIR;
export const skillsDir = () => join(dataDir(), "skills");
export const uploadsDir = () => join(dataDir(), "uploads");
export const knowledgeDir = (projectSlug?: string) => {
  const base = join(dataDir(), "knowledge");
  return projectSlug ? join(base, projectSlug) : base;
};
export const seedsSkillsDir = () => join(seedsDir(), "skills");
