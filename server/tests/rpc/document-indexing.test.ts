import { describe, it, expect, beforeEach } from "bun:test";
import { readFile } from "fs/promises";
import { join } from "path";
import { db } from "@/db/connection";
import { documentChunks, projectDocuments } from "@/db/schema";
import { eq } from "drizzle-orm";
import { request, registerAndLogin } from "../helpers";

const FIXTURES = join(import.meta.dir, "../fixtures");

async function rpc(path: string, input: unknown, token?: string) {
  return request("POST", `/rpc/${path.replace(/\./g, "/")}`, {
    body: { json: input } as Record<string, unknown>,
    token,
  });
}

async function rpcJson<T = unknown>(res: Response): Promise<T> {
  const body = await res.json();
  return (body?.json ?? body) as T;
}

async function waitForIndexed(docId: string, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const [doc] = await db
      .select({ status: projectDocuments.status, errorMessage: projectDocuments.errorMessage })
      .from(projectDocuments)
      .where(eq(projectDocuments.id, docId));
    if (doc && (doc.status === "indexed" || doc.status === "index_failed")) {
      return doc;
    }
    await Bun.sleep(300);
  }
  throw new Error(`Timeout waiting for document ${docId}`);
}

async function assertChunksExist(docId: string, expectKeyword: string) {
  const chunks = await db
    .select()
    .from(documentChunks)
    .where(eq(documentChunks.documentId, docId));

  expect(chunks.length).toBeGreaterThan(0);

  for (const chunk of chunks) {
    expect(chunk.content).toBeTruthy();
    expect(chunk.embedding).toBeTruthy();
    expect(chunk.embedding!.length).toBe(1024);
  }

  const all = chunks.map((c) => c.content).join(" ");
  expect(all).toContain(expectKeyword);

  return chunks;
}

// ── helpers: 两种上传方式 ────────────────────────────────

/** 通过 RPC 创建文本文档（适合纯文本内容） */
async function createTextDocument(
  token: string,
  projectId: string,
  filename: string,
  content: string,
) {
  const res = await rpc(
    "document.create",
    { projectId, filename, content, docType: "markdown" },
    token,
  );
  expect(res.status).toBe(200);
  return rpcJson<{ id: string; status: string }>(res);
}

/** 通过 REST 上传二进制文件 */
async function uploadFixtureFile(
  token: string,
  projectId: string,
  filename: string,
) {
  const bytes = await readFile(join(FIXTURES, filename));
  const file = new File([bytes], filename);
  const formData = new FormData();
  formData.append("file", file);

  const res = await request("POST", `/api/projects/${projectId}/documents/upload`, {
    token,
    formData,
  });
  expect(res.status).toBe(201);
  return res.json() as Promise<{ id: string }>;
}

// ── 测试 ─────────────────────────────────────────────────

describe("Document Indexing E2E", () => {
  let token: string;
  let projectId: string;

  beforeEach(async () => {
    token = await registerAndLogin();
    const res = await rpc("project.create", { name: "Indexing Test" }, token);
    projectId = (await rpcJson<{ id: string }>(res)).id;
  });

  // ── 文本格式（通过 RPC 创建） ──────────────────────────

  it("Markdown → chunks with embedding", async () => {
    const content = await readFile(join(FIXTURES, "sample.md"), "utf-8");
    const doc = await createTextDocument(token, projectId, "sample.md", content);
    const { status } = await waitForIndexed(doc.id);
    expect(status).toBe("indexed");
    await assertChunksExist(doc.id, "Kubernetes");
  }, 30000);

  it("JSON → chunks with embedding", async () => {
    const content = await readFile(join(FIXTURES, "sample.json"), "utf-8");
    const doc = await createTextDocument(token, projectId, "sample.json", content);
    const { status } = await waitForIndexed(doc.id);
    expect(status).toBe("indexed");
    await assertChunksExist(doc.id, "calico");
  }, 30000);

  it("XML → chunks with embedding", async () => {
    const content = await readFile(join(FIXTURES, "sample.xml"), "utf-8");
    const doc = await createTextDocument(token, projectId, "sample.xml", content);
    const { status } = await waitForIndexed(doc.id);
    expect(status).toBe("indexed");
    await assertChunksExist(doc.id, "api-gateway");
  }, 30000);

  it("TypeScript → chunks with embedding", async () => {
    const content = await readFile(join(FIXTURES, "sample.ts"), "utf-8");
    const doc = await createTextDocument(token, projectId, "sample.ts", content);
    const { status } = await waitForIndexed(doc.id);
    expect(status).toBe("indexed");
    await assertChunksExist(doc.id, "Hono");
  }, 30000);

  // ── 二进制格式（通过文件上传） ─────────────────────────

  it("PDF upload → parse → chunks with embedding", async () => {
    const doc = await uploadFixtureFile(token, projectId, "sample.pdf");
    const { status } = await waitForIndexed(doc.id);
    expect(status).toBe("indexed");
    const chunks = await assertChunksExist(doc.id, "MySQL");
    // PDF 应该有 page metadata
    expect(chunks[0].metadata).toHaveProperty("page");
  }, 30000);

  it("DOCX upload → parse → chunks with embedding", async () => {
    const doc = await uploadFixtureFile(token, projectId, "sample.docx");
    const { status } = await waitForIndexed(doc.id);
    expect(status).toBe("indexed");
    await assertChunksExist(doc.id, "Nginx");
  }, 30000);

  it("XLSX upload → parse → chunks with embedding", async () => {
    const doc = await uploadFixtureFile(token, projectId, "sample.xlsx");
    const { status } = await waitForIndexed(doc.id);
    expect(status).toBe("indexed");
    const chunks = await assertChunksExist(doc.id, "10.0");
    // XLSX 应该有 sheet metadata
    expect(chunks[0].metadata).toHaveProperty("sheet");
  }, 30000);

  // ── 内联文本上传 ───────────────────────────────────────

  it("plain text file upload → chunks with embedding", async () => {
    const content = "Redis 缓存配置说明\n\n默认端口 6379，最大内存 256MB。";
    const file = new File([content], "redis-config.txt", { type: "text/plain" });
    const formData = new FormData();
    formData.append("file", file);

    const res = await request("POST", `/api/projects/${projectId}/documents/upload`, {
      token,
      formData,
    });
    expect(res.status).toBe(201);
    const doc = (await res.json()) as { id: string };

    const { status } = await waitForIndexed(doc.id);
    expect(status).toBe("indexed");
    await assertChunksExist(doc.id, "Redis");
  }, 30000);

  // ── 更新后重新索引 ────────────────────────────────────

  it("update document → re-index with new chunks", async () => {
    // 创建初始文档
    const doc = await createTextDocument(
      token, projectId, "evolve.md", "# 初始内容\n\nPostgreSQL 主从配置",
    );
    await waitForIndexed(doc.id);

    const oldChunks = await db.select().from(documentChunks)
      .where(eq(documentChunks.documentId, doc.id));
    expect(oldChunks.length).toBeGreaterThan(0);
    const oldIds = oldChunks.map((c) => c.id);

    // 更新为完全不同的内容
    await rpc("document.update", { id: doc.id, content: "# 新内容\n\nElasticsearch 集群调优指南" }, token);
    await waitForIndexed(doc.id);

    // 验证：旧 chunks 消失，新 chunks 包含新关键词
    const newChunks = await db.select().from(documentChunks)
      .where(eq(documentChunks.documentId, doc.id));
    expect(newChunks.length).toBeGreaterThan(0);
    expect(newChunks.every((c) => !oldIds.includes(c.id))).toBe(true);

    const allContent = newChunks.map((c) => c.content).join(" ");
    expect(allContent).toContain("Elasticsearch");
    expect(allContent).not.toContain("PostgreSQL");

    for (const chunk of newChunks) {
      expect(chunk.embedding!.length).toBe(1024);
    }
  }, 60000);

  // ── 删除文档级联清理 chunks ────────────────────────────

  it("delete document → cascade delete chunks", async () => {
    const doc = await createTextDocument(
      token, projectId, "ephemeral.md", "# 临时文档\n\nKafka 消费者组配置",
    );
    await waitForIndexed(doc.id);

    const chunks = await db.select().from(documentChunks)
      .where(eq(documentChunks.documentId, doc.id));
    expect(chunks.length).toBeGreaterThan(0);

    // 删除文档
    const res = await rpc("document.remove", { id: doc.id }, token);
    expect(res.status).toBe(200);

    // chunks 应该被级联删除
    const remaining = await db.select().from(documentChunks)
      .where(eq(documentChunks.documentId, doc.id));
    expect(remaining.length).toBe(0);
  }, 30000);

  // ── 删除项目级联清理 ──────────────────────────────────

  it("delete project → cascade delete all documents and chunks", async () => {
    // 创建两个文档
    const doc1 = await createTextDocument(
      token, projectId, "doc1.md", "# 文档一\n\nDocker Compose 编排",
    );
    const doc2 = await createTextDocument(
      token, projectId, "doc2.md", "# 文档二\n\nPrometheus 监控配置",
    );
    await Promise.all([waitForIndexed(doc1.id), waitForIndexed(doc2.id)]);

    // 确认 chunks 存在
    const chunksBefore = await db.select().from(documentChunks)
      .where(eq(documentChunks.projectId, projectId));
    expect(chunksBefore.length).toBeGreaterThan(0);

    // 删除项目
    const res = await rpc("project.remove", { id: projectId }, token);
    expect(res.status).toBe(200);

    // 项目下的文档和 chunks 全部清除
    const docsAfter = await db.select().from(projectDocuments)
      .where(eq(projectDocuments.projectId, projectId));
    expect(docsAfter.length).toBe(0);

    const chunksAfter = await db.select().from(documentChunks)
      .where(eq(documentChunks.projectId, projectId));
    expect(chunksAfter.length).toBe(0);
  }, 60000);

  // ── 图片上传 + Vision API ─────────────────────────────

  it("PNG upload → Vision API describe → chunks with embedding", async () => {
    const doc = await uploadFixtureFile(token, projectId, "sample.png");
    const { status } = await waitForIndexed(doc.id, 60000);
    expect(status).toBe("indexed");

    // 验证文档内容非空（Vision API 生成的描述）
    const [fullDoc] = await db.select().from(projectDocuments)
      .where(eq(projectDocuments.id, doc.id));
    expect(fullDoc.content.length).toBeGreaterThan(10);

    // 验证 chunks 及 metadata
    const chunks = await db.select().from(documentChunks)
      .where(eq(documentChunks.documentId, doc.id));
    expect(chunks.length).toBeGreaterThan(0);
    expect(chunks[0].embedding!.length).toBe(1024);
    expect(chunks[0].metadata).toHaveProperty("source", "vision_description");
  }, 90000);
});
