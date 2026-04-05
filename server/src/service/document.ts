import { db } from "@/db/connection";
import { projectDocuments, documentChunks, projects } from "@/db/schema";
import { eq } from "drizzle-orm";
import { NotFoundError, BadRequestError } from "@/lib/errors";
import { knowledgeDir } from "@/lib/paths";
import { logger } from "@/lib/logger";
import { parseFile, type ParsedSegment } from "@/lib/file-parser";
import { chunkSegments } from "@/lib/chunker";
import { embedTexts } from "@/lib/embedder";
import { join, extname } from "path";
import { mkdir } from "fs/promises";

const DOC_TYPE_MAP: Record<string, string> = {
  pdf: "pdf",
  docx: "word",
  doc: "word",
  xlsx: "excel",
  xls: "excel",
  csv: "csv",
  md: "markdown",
  txt: "text",
  pptx: "pptx",
  ppt: "pptx",
  html: "html",
  htm: "html",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  log: "log",
  png: "image",
  jpg: "image",
  jpeg: "image",
  gif: "image",
  webp: "image",
};

export async function save(input: {
  projectId: string;
  filename: string;
  content: string;
  docType: string;
  status?: string;
}) {
  const [doc] = await db
    .insert(projectDocuments)
    .values({
      projectId: input.projectId,
      filename: input.filename,
      content: input.content,
      docType: input.docType,
      status: input.status ?? "pending",
    })
    .returning();
  return doc;
}

export async function get(id: string) {
  const [doc] = await db
    .select()
    .from(projectDocuments)
    .where(eq(projectDocuments.id, id));
  if (!doc) throw new NotFoundError("Document not found");
  return doc;
}

export async function listByProject(projectId: string) {
  return db
    .select()
    .from(projectDocuments)
    .where(eq(projectDocuments.projectId, projectId));
}

export async function update(id: string, content: string) {
  const [doc] = await db
    .select()
    .from(projectDocuments)
    .where(eq(projectDocuments.id, id));
  if (!doc) throw new NotFoundError("Document not found");

  const isMemoryConfig = doc.docType === "memory_config";

  // memory_config: keep indexed; others: set pending for re-indexing
  const [updated] = await db
    .update(projectDocuments)
    .set({
      content,
      status: isMemoryConfig ? "indexed" : "pending",
    })
    .where(eq(projectDocuments.id, id))
    .returning();

  // Write to filesystem
  const [project] = await db
    .select()
    .from(projects)
    .where(eq(projects.id, doc.projectId));
  if (project) {
    const dir = knowledgeDir(project.slug);
    await mkdir(dir, { recursive: true });
    await Bun.write(join(dir, doc.filename), content);
  }

  // Non-memory_config with content: trigger background re-indexing
  if (!isMemoryConfig && content.trim()) {
    indexDocument(doc.id, doc.projectId, content, null).catch((err) => {
      logger.error({ err, documentId: doc.id }, "Background re-indexing failed");
    });
  }

  return updated;
}

export async function remove(id: string) {
  const [doc] = await db
    .select()
    .from(projectDocuments)
    .where(eq(projectDocuments.id, id));
  if (!doc) throw new NotFoundError("Document not found");
  if (doc.docType === "memory_config") {
    throw new BadRequestError("MEMORY.md 文档不可删除");
  }

  // Chunks cascade-deleted via FK
  await db.delete(projectDocuments).where(eq(projectDocuments.id, id));
}

export async function saveUploadedFile(
  projectId: string,
  file: File,
): Promise<typeof projectDocuments.$inferSelect> {
  const filename = file.name || "unknown";
  const ext = extname(filename).slice(1).toLowerCase();
  const bytes = new Uint8Array(await file.arrayBuffer());

  // Get project for slug
  const [project] = await db
    .select()
    .from(projects)
    .where(eq(projects.id, projectId));
  if (!project) throw new NotFoundError("Project not found");

  // Store file to disk
  const dir = knowledgeDir(project.slug);
  await mkdir(dir, { recursive: true });
  const filePath = join(dir, filename);
  await Bun.write(filePath, bytes);

  // Parse file
  let segments: ParsedSegment[];
  try {
    segments = await parseFile(filePath, filename);
  } catch (err) {
    logger.error({ err, filename }, "Failed to parse file");
    segments = [];
  }

  const content = segments.map((s) => s.content).join("\n\n");
  const docType = DOC_TYPE_MAP[ext] || "text";
  const isEmpty = !content.trim();

  // Save document record
  const [doc] = await db
    .insert(projectDocuments)
    .values({
      projectId,
      filename,
      content,
      docType,
      status: isEmpty ? "indexed" : "pending",
    })
    .returning();

  // Background indexing
  if (!isEmpty) {
    indexDocument(doc.id, projectId, content, segments).catch((err) => {
      logger.error({ err, documentId: doc.id }, "Background indexing failed");
    });
  }

  return doc;
}

/**
 * 后台索引文档：分块 → embedding → 存入 document_chunks
 */
export async function indexDocument(
  documentId: string,
  projectId: string,
  content: string,
  segments: ParsedSegment[] | null,
): Promise<void> {
  try {
    // 1. Set status to indexing
    await db
      .update(projectDocuments)
      .set({ status: "indexing" })
      .where(eq(projectDocuments.id, documentId));

    // 2. Delete old chunks
    await db
      .delete(documentChunks)
      .where(eq(documentChunks.documentId, documentId));

    // 3. Chunk
    const inputSegments: ParsedSegment[] = segments ?? [
      { content, metadata: {} },
    ];
    const chunks = chunkSegments(inputSegments);

    if (!chunks.length) {
      await db
        .update(projectDocuments)
        .set({ status: "indexed", errorMessage: null })
        .where(eq(projectDocuments.id, documentId));
      return;
    }

    // 4. Embed
    const embeddings = await embedTexts(chunks.map((c) => c.content));

    // 5. Insert chunks
    await db.insert(documentChunks).values(
      chunks.map((chunk, i) => ({
        documentId,
        projectId,
        chunkIndex: chunk.index,
        content: chunk.content,
        embedding: embeddings[i],
        metadata: chunk.metadata,
      })),
    );

    // 6. Set status to indexed
    await db
      .update(projectDocuments)
      .set({ status: "indexed", errorMessage: null })
      .where(eq(projectDocuments.id, documentId));

    logger.info(
      { documentId, chunkCount: chunks.length },
      "Document indexed successfully",
    );
  } catch (err) {
    logger.error({ err, documentId }, "Document indexing failed");
    await db
      .update(projectDocuments)
      .set({
        status: "index_failed",
        errorMessage: err instanceof Error ? err.message : "Unknown error",
      })
      .where(eq(projectDocuments.id, documentId));
  }
}

export function toResponse(doc: typeof projectDocuments.$inferSelect) {
  return {
    id: doc.id,
    projectId: doc.projectId,
    filename: doc.filename,
    docType: doc.docType,
    status: doc.status,
    errorMessage: doc.errorMessage,
    createdAt: doc.createdAt.toISOString(),
    updatedAt: doc.updatedAt.toISOString(),
  };
}

export function toDetailResponse(doc: typeof projectDocuments.$inferSelect) {
  return {
    ...toResponse(doc),
    content: doc.content,
  };
}
