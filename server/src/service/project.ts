import { db } from "@/db/connection";
import { projects, projectDocuments } from "@/db/schema";
import { count, desc, eq } from "drizzle-orm";
import { NotFoundError } from "@/lib/errors";
import { knowledgeDir } from "@/lib/paths";
import { mkdir, rm } from "fs/promises";

function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export async function create(input: { name: string; slug?: string | null; description?: string | null }) {
  const slug = input.slug || generateSlug(input.name);

  const [project] = await db
    .insert(projects)
    .values({ name: input.name, slug, description: input.description })
    .returning();

  // Create MEMORY.md document
  await db.insert(projectDocuments).values({
    projectId: project.id,
    filename: "MEMORY.md",
    content: "",
    docType: "memory_config",
    status: "indexed",
  });

  // Ensure knowledge directory exists
  const dir = knowledgeDir(slug);
  await mkdir(dir, { recursive: true });

  return project;
}

export async function get(id: string) {
  const [project] = await db.select().from(projects).where(eq(projects.id, id));
  if (!project) throw new NotFoundError("Project not found");
  return project;
}

export async function list(page: number, pageSize: number) {
  const [items, [{ value: total }]] = await Promise.all([
    db.select().from(projects).orderBy(desc(projects.createdAt)).offset((page - 1) * pageSize).limit(pageSize),
    db.select({ value: count() }).from(projects),
  ]);
  return { items, total, page, pageSize };
}

export async function update(id: string, input: { name?: string; description?: string | null }) {
  const [existing] = await db.select().from(projects).where(eq(projects.id, id));
  if (!existing) throw new NotFoundError("Project not found");

  const set: Record<string, unknown> = {};
  if (input.name !== undefined) set.name = input.name;
  if (input.description !== undefined) set.description = input.description;

  const [updated] = await db.update(projects).set(set).where(eq(projects.id, id)).returning();
  return updated;
}

export async function remove(id: string) {
  const [project] = await db.select().from(projects).where(eq(projects.id, id));
  if (!project) throw new NotFoundError("Project not found");

  await db.delete(projects).where(eq(projects.id, id));

  // Cleanup knowledge directory
  try {
    await rm(knowledgeDir(project.slug), { recursive: true, force: true });
  } catch {
    // ignore if directory doesn't exist
  }
}

export function toResponse(project: typeof projects.$inferSelect) {
  return {
    id: project.id,
    name: project.name,
    slug: project.slug,
    description: project.description,
    createdAt: project.createdAt.toISOString(),
    updatedAt: project.updatedAt.toISOString(),
  };
}
