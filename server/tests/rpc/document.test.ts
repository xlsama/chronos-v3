import { describe, it, expect, beforeEach } from "bun:test";
import { request, registerAndLogin } from "../helpers";

async function rpc(path: string, input: unknown, token?: string) {
  const urlPath = `/rpc/${path.replace(/\./g, "/")}`;
  return request("POST", urlPath, {
    body: { json: input } as Record<string, unknown>,
    token,
  });
}

async function rpcJson<T = unknown>(res: Response): Promise<T> {
  const body = await res.json();
  return (body?.json ?? body) as T;
}

async function createProject(token: string, name = "Test Project") {
  const res = await rpc("project.create", { name }, token);
  return rpcJson<{ id: string }>(res);
}

describe("Document RPC", () => {
  let token: string;
  let projectId: string;

  beforeEach(async () => {
    token = await registerAndLogin();
    const project = await createProject(token);
    projectId = project.id;
  });

  describe("document.create", () => {
    it("should create a markdown document", async () => {
      const res = await rpc(
        "document.create",
        { projectId, filename: "test.md", content: "# Hello\n\nWorld", docType: "markdown" },
        token,
      );
      expect(res.status).toBe(200);
      const doc = await rpcJson<{ filename: string; docType: string; projectId: string }>(res);
      expect(doc.filename).toBe("test.md");
      expect(doc.docType).toBe("markdown");
      expect(doc.projectId).toBe(projectId);
    });

    it("should set empty document status to indexed", async () => {
      const res = await rpc(
        "document.create",
        { projectId, filename: "empty.md", content: "" },
        token,
      );
      const doc = await rpcJson<{ status: string }>(res);
      expect(doc.status).toBe("indexed");
    });
  });

  describe("document.listByProject", () => {
    it("should list documents including MEMORY.md", async () => {
      await rpc("document.create", { projectId, filename: "doc.md", content: "test" }, token);

      const res = await rpc("document.listByProject", { projectId }, token);
      const docs = await rpcJson<Array<{ filename: string }>>(res);
      expect(docs.length).toBeGreaterThanOrEqual(2);
      expect(docs.some((d) => d.filename === "MEMORY.md")).toBe(true);
      expect(docs.some((d) => d.filename === "doc.md")).toBe(true);
    });
  });

  describe("document.get", () => {
    it("should get document with content", async () => {
      const createRes = await rpc(
        "document.create",
        { projectId, filename: "detail.md", content: "detailed content" },
        token,
      );
      const { id } = await rpcJson<{ id: string }>(createRes);

      const res = await rpc("document.get", { id }, token);
      expect(res.status).toBe(200);
      const doc = await rpcJson<{ content: string; filename: string }>(res);
      expect(doc.content).toBe("detailed content");
      expect(doc.filename).toBe("detail.md");
    });
  });

  describe("document.update", () => {
    it("should update document content", async () => {
      const createRes = await rpc(
        "document.create",
        { projectId, filename: "edit.md", content: "old" },
        token,
      );
      const { id } = await rpcJson<{ id: string }>(createRes);

      const res = await rpc("document.update", { id, content: "new content" }, token);
      expect(res.status).toBe(200);
      const doc = await rpcJson<{ content: string }>(res);
      expect(doc.content).toBe("new content");
    });
  });

  describe("document.remove", () => {
    it("should delete non-memory document", async () => {
      const createRes = await rpc(
        "document.create",
        { projectId, filename: "delete.md", content: "bye" },
        token,
      );
      const { id } = await rpcJson<{ id: string }>(createRes);

      const res = await rpc("document.remove", { id }, token);
      expect(res.status).toBe(200);

      const getRes = await rpc("document.get", { id }, token);
      expect(getRes.status).toBe(404);
    });

    it("should reject deleting MEMORY.md", async () => {
      const docsRes = await rpc("document.listByProject", { projectId }, token);
      const docs = await rpcJson<Array<{ id: string; docType: string }>>(docsRes);
      const memoryDoc = docs.find((d) => d.docType === "memory_config");
      expect(memoryDoc).toBeDefined();

      const res = await rpc("document.remove", { id: memoryDoc!.id }, token);
      expect(res.status).toBe(400);
    });
  });
});
