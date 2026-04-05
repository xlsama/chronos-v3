import { describe, it, expect, beforeEach } from "bun:test";
import { request, json, registerAndLogin } from "./helpers";

describe("Servers API", () => {
  let token: string;

  beforeEach(async () => {
    token = await registerAndLogin();
  });

  describe("POST /api/servers", () => {
    it("should create a server", async () => {
      const res = await request("POST", "/api/servers", {
        token,
        body: { name: "test-server", host: "192.168.1.1", port: 22, username: "root" },
      });
      expect(res.status).toBe(201);
      const data = await json<{ id: string; name: string; host: string; authMethod: string }>(res);
      expect(data.name).toBe("test-server");
      expect(data.host).toBe("192.168.1.1");
      expect(data.authMethod).toBe("none");
    });

    it("should set authMethod to password when password provided", async () => {
      const res = await request("POST", "/api/servers", {
        token,
        body: { name: "pw-server", host: "10.0.0.1", password: "secret" },
      });
      const data = await json<{ authMethod: string }>(res);
      expect(data.authMethod).toBe("password");
    });

    it("should reject duplicate name", async () => {
      await request("POST", "/api/servers", {
        token,
        body: { name: "dup-server", host: "10.0.0.1" },
      });
      const res = await request("POST", "/api/servers", {
        token,
        body: { name: "dup-server", host: "10.0.0.2" },
      });
      expect(res.status).toBe(422);
    });

    it("should require auth", async () => {
      const res = await request("POST", "/api/servers", {
        body: { name: "no-auth", host: "10.0.0.1" },
      });
      expect(res.status).toBe(401);
    });
  });

  describe("GET /api/servers", () => {
    it("should list servers with pagination", async () => {
      await request("POST", "/api/servers", {
        token,
        body: { name: "s1", host: "10.0.0.1" },
      });
      await request("POST", "/api/servers", {
        token,
        body: { name: "s2", host: "10.0.0.2" },
      });

      const res = await request("GET", "/api/servers", { token });
      expect(res.status).toBe(200);
      const data = await json<{ items: unknown[]; total: number; page: number; pageSize: number }>(res);
      expect(data.items).toHaveLength(2);
      expect(data.total).toBe(2);
      expect(data.page).toBe(1);
    });
  });

  describe("GET /api/servers/:id", () => {
    it("should return a server by id", async () => {
      const createRes = await request("POST", "/api/servers", {
        token,
        body: { name: "get-me", host: "10.0.0.1" },
      });
      const { id } = await json<{ id: string }>(createRes);

      const res = await request("GET", `/api/servers/${id}`, { token });
      expect(res.status).toBe(200);
      const data = await json<{ name: string }>(res);
      expect(data.name).toBe("get-me");
    });

    it("should return 404 for non-existent", async () => {
      const res = await request("GET", "/api/servers/00000000-0000-0000-0000-000000000000", { token });
      expect(res.status).toBe(404);
    });
  });

  describe("PATCH /api/servers/:id", () => {
    it("should update a server", async () => {
      const createRes = await request("POST", "/api/servers", {
        token,
        body: { name: "update-me", host: "10.0.0.1" },
      });
      const { id } = await json<{ id: string }>(createRes);

      const res = await request("PATCH", `/api/servers/${id}`, {
        token,
        body: { host: "10.0.0.99", port: 2222 },
      });
      expect(res.status).toBe(200);
      const data = await json<{ host: string; port: number }>(res);
      expect(data.host).toBe("10.0.0.99");
      expect(data.port).toBe(2222);
    });
  });

  describe("DELETE /api/servers/:id", () => {
    it("should delete a server", async () => {
      const createRes = await request("POST", "/api/servers", {
        token,
        body: { name: "delete-me", host: "10.0.0.1" },
      });
      const { id } = await json<{ id: string }>(createRes);

      const res = await request("DELETE", `/api/servers/${id}`, { token });
      expect(res.status).toBe(204);

      const getRes = await request("GET", `/api/servers/${id}`, { token });
      expect(getRes.status).toBe(404);
    });
  });

  describe("POST /api/servers/batch", () => {
    it("should batch create servers", async () => {
      const res = await request("POST", "/api/servers/batch", {
        token,
        body: {
          items: [
            { name: "b1", host: "10.0.0.1" },
            { name: "b2", host: "10.0.0.2" },
          ],
        },
      });
      expect(res.status).toBe(200);
      const data = await json<{ created: number; skipped: number; errors: string[] }>(res);
      expect(data.created).toBe(2);
      expect(data.skipped).toBe(0);
      expect(data.errors).toHaveLength(0);
    });

    it("should skip duplicates in batch", async () => {
      await request("POST", "/api/servers", {
        token,
        body: { name: "existing", host: "10.0.0.1" },
      });
      const res = await request("POST", "/api/servers/batch", {
        token,
        body: {
          items: [
            { name: "existing", host: "10.0.0.1" },
            { name: "new-one", host: "10.0.0.2" },
          ],
        },
      });
      const data = await json<{ created: number; skipped: number }>(res);
      expect(data.created).toBe(1);
      expect(data.skipped).toBe(1);
    });
  });
});
