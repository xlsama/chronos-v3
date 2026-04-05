import { readdir, readFile, writeFile, mkdir, rm, stat } from "fs/promises";
import { join } from "path";
import { existsSync } from "fs";
import { parse as parseYaml } from "yaml";
import { skillsDir } from "@/lib/paths";

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const ALLOWED_SUBDIRS = new Set(["scripts", "references", "assets"]);

export interface SkillMeta {
  slug: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  hasScripts: boolean;
  hasReferences: boolean;
  hasAssets: boolean;
  scriptFiles: string[];
  referenceFiles: string[];
  assetFiles: string[];
  draft: boolean;
  whenToUse: string;
  tags: string[];
  relatedServices: string[];
}

function parseSkillFile(text: string): { frontmatter: Record<string, unknown>; body: string } {
  if (!text.startsWith("---")) return { frontmatter: {}, body: text };
  const parts = text.split("---", 3);
  if (parts.length < 3) return { frontmatter: {}, body: text };
  const frontmatter = (parseYaml(parts[1]) as Record<string, unknown>) || {};
  const body = parts[2].replace(/^\n+/, "");
  return { frontmatter, body };
}

async function listFiles(dir: string): Promise<string[]> {
  try {
    const entries = await readdir(dir, { withFileTypes: true });
    return entries.filter((e) => e.isFile()).map((e) => e.name).sort();
  } catch {
    return [];
  }
}

async function buildMeta(slug: string, skillDir: string): Promise<SkillMeta> {
  const skillFile = join(skillDir, "SKILL.md");
  let frontmatter: Record<string, unknown> = {};
  try {
    const text = await readFile(skillFile, "utf-8");
    frontmatter = parseSkillFile(text).frontmatter;
  } catch {
    // no SKILL.md or parse error
  }

  const stats = await stat(skillDir);
  const scriptFiles = await listFiles(join(skillDir, "scripts"));
  const referenceFiles = await listFiles(join(skillDir, "references"));
  const assetFiles = await listFiles(join(skillDir, "assets"));

  const rawTags = frontmatter.tags;
  const tags = typeof rawTags === "string"
    ? rawTags.split(",").map((t) => t.trim()).filter(Boolean)
    : Array.isArray(rawTags) ? rawTags.map(String) : [];

  const rawServices = frontmatter.related_services;
  const relatedServices = typeof rawServices === "string"
    ? rawServices.split(",").map((s) => s.trim()).filter(Boolean)
    : Array.isArray(rawServices) ? rawServices.map(String) : [];

  return {
    slug,
    name: String(frontmatter.name || slug),
    description: String(frontmatter.description || ""),
    createdAt: stats.birthtime.toISOString(),
    updatedAt: stats.mtime.toISOString(),
    hasScripts: scriptFiles.length > 0,
    hasReferences: referenceFiles.length > 0,
    hasAssets: assetFiles.length > 0,
    scriptFiles,
    referenceFiles,
    assetFiles,
    draft: Boolean(frontmatter.draft),
    whenToUse: String(frontmatter.when_to_use || ""),
    tags,
    relatedServices,
  };
}

function safeRelPath(slug: string, relPath: string): string {
  if (relPath.includes("..") || relPath.startsWith("/") || relPath.startsWith("~")) {
    throw new Error(`非法路径: ${relPath}`);
  }
  const parts = relPath.split("/");
  if (parts.length < 2 || !ALLOWED_SUBDIRS.has(parts[0])) {
    throw new Error(`路径必须在 scripts/, references/, assets/ 目录下`);
  }
  return join(skillsDir(), slug, relPath);
}

export async function listSkills(): Promise<SkillMeta[]> {
  const baseDir = skillsDir();
  try {
    const entries = await readdir(baseDir, { withFileTypes: true });
    const results: SkillMeta[] = [];
    for (const entry of entries.filter((e) => e.isDirectory()).sort((a, b) => a.name.localeCompare(b.name))) {
      const skillFile = join(baseDir, entry.name, "SKILL.md");
      if (existsSync(skillFile)) {
        results.push(await buildMeta(entry.name, join(baseDir, entry.name)));
      }
    }
    return results;
  } catch {
    return [];
  }
}

export async function getSkill(slug: string): Promise<{ meta: SkillMeta; content: string }> {
  const skillDir = join(skillsDir(), slug);
  const skillFile = join(skillDir, "SKILL.md");
  let text: string;
  try {
    text = await readFile(skillFile, "utf-8");
  } catch {
    throw new Error(`Skill '${slug}' not found`);
  }

  const meta = await buildMeta(slug, skillDir);
  const { body } = parseSkillFile(text);
  return { meta, content: body };
}

export async function createSkill(slug: string): Promise<SkillMeta> {
  if (!SLUG_RE.test(slug) || slug.length > 64) {
    throw new Error("Slug 格式不正确");
  }

  const skillDir = join(skillsDir(), slug);
  if (existsSync(skillDir)) {
    throw new Error(`Skill '${slug}' already exists`);
  }

  await mkdir(skillDir, { recursive: true });
  const content = `---\nname: ${slug}\ndescription: ""\ndraft: true\n---\n\n`;
  await writeFile(join(skillDir, "SKILL.md"), content, "utf-8");
  return buildMeta(slug, skillDir);
}

export async function updateSkill(slug: string, content: string): Promise<SkillMeta> {
  const skillDir = join(skillsDir(), slug);
  const skillFile = join(skillDir, "SKILL.md");
  if (!existsSync(skillFile)) {
    throw new Error(`Skill '${slug}' not found`);
  }
  await writeFile(skillFile, content, "utf-8");
  return buildMeta(slug, skillDir);
}

export async function deleteSkill(slug: string): Promise<void> {
  const skillDir = join(skillsDir(), slug);
  if (!existsSync(skillDir)) {
    throw new Error(`Skill '${slug}' not found`);
  }
  await rm(skillDir, { recursive: true, force: true });
}

export async function readSkillFile(slug: string, relPath: string): Promise<string> {
  const fullPath = safeRelPath(slug, relPath);
  try {
    return await readFile(fullPath, "utf-8");
  } catch {
    throw new Error(`File '${relPath}' not found in skill '${slug}'`);
  }
}

export async function writeSkillFile(slug: string, relPath: string, content: string): Promise<void> {
  const fullPath = safeRelPath(slug, relPath);
  const dir = join(fullPath, "..");
  await mkdir(dir, { recursive: true });
  await writeFile(fullPath, content, "utf-8");
}

export async function deleteSkillFile(slug: string, relPath: string): Promise<void> {
  const fullPath = safeRelPath(slug, relPath);
  const { unlink } = await import("fs/promises");
  try {
    await unlink(fullPath);
  } catch {
    throw new Error(`File '${relPath}' not found in skill '${slug}'`);
  }
}

export function toResponse(meta: SkillMeta) {
  return {
    slug: meta.slug,
    name: meta.name,
    description: meta.description,
    hasScripts: meta.hasScripts,
    hasReferences: meta.hasReferences,
    hasAssets: meta.hasAssets,
    draft: meta.draft,
    whenToUse: meta.whenToUse,
    tags: meta.tags,
    relatedServices: meta.relatedServices,
    createdAt: meta.createdAt,
    updatedAt: meta.updatedAt,
  };
}

export function toDetailResponse(meta: SkillMeta, content: string) {
  return {
    ...toResponse(meta),
    content,
    scriptFiles: meta.scriptFiles,
    referenceFiles: meta.referenceFiles,
    assetFiles: meta.assetFiles,
  };
}
