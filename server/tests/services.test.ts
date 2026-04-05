import { describe, it, expect, beforeEach } from "bun:test";
import { request, json, registerAndLogin } from "./helpers";

describe("Services API", () => {
  let token: string;

  beforeEach(async () => {
    token = await registerAndLogin();
  });

  describe("POST /api/services", () => {
    it("should create a service", async () => {
      const res = await request("POST", "/api/services", {
        token,
        body: { name: "test-pg", serviceType: "postgresql", host: "localhost", port: 5432 },
      });
      expect(res.status).toBe(201);
      const data = await json<{ name: string; serviceType: string; hasPassword: boolean }>(res);
      expect(data.name).toBe("test-pg");
      expect(data.serviceType).toBe("postgresql");
      expect(data.hasPassword).toBe(false);
    });

    it("should set hasPassword when password provided", async () => {
      const res = await request("POST", "/api/services", {
        token,
        body: { name: "pw-svc", serviceType: "redis", host: "localhost", port: 6379, password: "secret" },
      });
      const data = await json<{ hasPassword: boolean }>(res);
      expect(data.hasPassword).toBe(true);
    });

    it("should reject duplicate name", async () => {
      await request("POST", "/api/services", {
        token,
        body: { name: "dup-svc", serviceType: "redis", host: "localhost", port: 6379 },
      });
      const res = await request("POST", "/api/services", {
        token,
        body: { name: "dup-svc", serviceType: "mysql", host: "localhost", port: 3306 },
      });
      expect(res.status).toBe(422);
    });
  });

  describe("GET /api/services", () => {
    it("should list with type filter", async () => {
      await request("POST", "/api/services", {
        token,
        body: { name: "pg1", serviceType: "postgresql", host: "localhost", port: 5432 },
      });
      await request("POST", "/api/services", {
        token,
        body: { name: "redis1", serviceType: "redis", host: "localhost", port: 6379 },
      });

      const allRes = await request("GET", "/api/services", { token });
      const all = await json<{ items: unknown[]; total: number }>(allRes);
      expect(all.total).toBe(2);

      const pgRes = await request("GET", "/api/services?type=postgresql", { token });
      const pg = await json<{ items: unknown[]; total: number }>(pgRes);
      expect(pg.total).toBe(1);
    });
  });

  describe("PATCH /api/services/:id", () => {
    it("should update a service", async () => {
      const createRes = await request("POST", "/api/services", {
        token,
        body: { name: "update-svc", serviceType: "redis", host: "localhost", port: 6379 },
      });
      const { id } = await json<{ id: string }>(createRes);

      const res = await request("PATCH", `/api/services/${id}`, {
        token,
        body: { port: 6380 },
      });
      expect(res.status).toBe(200);
      const data = await json<{ port: number }>(res);
      expect(data.port).toBe(6380);
    });
  });

  describe("DELETE /api/services/:id", () => {
    it("should delete a service", async () => {
      const createRes = await request("POST", "/api/services", {
        token,
        body: { name: "del-svc", serviceType: "redis", host: "localhost", port: 6379 },
      });
      const { id } = await json<{ id: string }>(createRes);

      const res = await request("DELETE", `/api/services/${id}`, { token });
      expect(res.status).toBe(204);
    });
  });
});
