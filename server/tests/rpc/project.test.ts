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

describe("Project RPC", () => {
  let token: string;

  beforeEach(async () => {
    token = await registerAndLogin();
  });

  describe("project.create", () => {
    it("should create a project with auto slug", async () => {
      const res = await rpc("project.create", { name: "My Test Project" }, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<{ name: string; slug: string }>(res);
      expect(data.name).toBe("My Test Project");
      expect(data.slug).toBe("my-test-project");
    });

    it("should auto-create MEMORY.md", async () => {
      const createRes = await rpc("project.create", { name: "With Memory" }, token);
      const { id } = await rpcJson<{ id: string }>(createRes);

      const docsRes = await rpc("document.listByProject", { projectId: id }, token);
      const docs = await rpcJson<Array<{ filename: string; docType: string }>>(docsRes);
      expect(docs).toHaveLength(1);
      expect(docs[0].filename).toBe("MEMORY.md");
      expect(docs[0].docType).toBe("memory_config");
    });
  });

  describe("project.list", () => {
    it("should list projects with pagination", async () => {
      await rpc("project.create", { name: "P1" }, token);
      await rpc("project.create", { name: "P2" }, token);

      const res = await rpc("project.list", { page: 1, pageSize: 50 }, token);
      const data = await rpcJson<{ items: unknown[]; total: number }>(res);
      expect(data.items).toHaveLength(2);
      expect(data.total).toBe(2);
    });
  });

  describe("project.get", () => {
    it("should get project by id", async () => {
      const createRes = await rpc("project.create", { name: "Get Me" }, token);
      const { id } = await rpcJson<{ id: string }>(createRes);

      const res = await rpc("project.get", { id }, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<{ name: string }>(res);
      expect(data.name).toBe("Get Me");
    });

    it("should return 404 for non-existent project", async () => {
      const res = await rpc("project.get", { id: "00000000-0000-0000-0000-000000000000" }, token);
      expect(res.status).toBe(404);
    });
  });

  describe("project.update", () => {
    it("should update project name", async () => {
      const createRes = await rpc("project.create", { name: "Old Name" }, token);
      const { id } = await rpcJson<{ id: string }>(createRes);

      const res = await rpc("project.update", { id, name: "New Name" }, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<{ name: string }>(res);
      expect(data.name).toBe("New Name");
    });
  });

  describe("project.remove", () => {
    it("should delete project", async () => {
      const createRes = await rpc("project.create", { name: "Delete Me" }, token);
      const { id } = await rpcJson<{ id: string }>(createRes);

      const deleteRes = await rpc("project.remove", { id }, token);
      expect(deleteRes.status).toBe(200);
      const data = await rpcJson<{ ok: boolean }>(deleteRes);
      expect(data.ok).toBe(true);

      const getRes = await rpc("project.get", { id }, token);
      expect(getRes.status).toBe(404);
    });
  });
});
