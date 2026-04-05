import { describe, it, expect, beforeEach } from "bun:test";
import { request, json, registerAndLogin } from "./helpers";
import * as versionService from "@/service/version";

describe("Versions API", () => {
  let token: string;

  beforeEach(async () => {
    token = await registerAndLogin();
  });

  describe("GET /api/versions", () => {
    it("should list versions for an entity", async () => {
      await versionService.saveVersion("skill", "my-skill", "v1 content", "init");
      await versionService.saveVersion("skill", "my-skill", "v2 content", "manual");

      const res = await request("GET", "/api/versions?entityType=skill&entityId=my-skill", { token });
      expect(res.status).toBe(200);
      const data = await json<Array<{ versionNumber: number; changeSource: string }>>(res);
      expect(data).toHaveLength(2);
      expect(data[0].versionNumber).toBe(2); // DESC order
      expect(data[1].versionNumber).toBe(1);
    });

    it("should return empty for non-existent entity", async () => {
      const res = await request("GET", "/api/versions?entityType=skill&entityId=nope", { token });
      const data = await json<unknown[]>(res);
      expect(data).toHaveLength(0);
    });

    it("should require entityType and entityId", async () => {
      const res = await request("GET", "/api/versions", { token });
      expect(res.status).toBe(422);
    });
  });

  describe("GET /api/versions/:id", () => {
    it("should return version detail with content", async () => {
      const version = await versionService.saveVersion("skill", "detail-skill", "the content", "init");

      const res = await request("GET", `/api/versions/${version.id}`, { token });
      expect(res.status).toBe(200);
      const data = await json<{ content: string; versionNumber: number }>(res);
      expect(data.content).toBe("the content");
      expect(data.versionNumber).toBe(1);
    });

    it("should return 404 for non-existent", async () => {
      const res = await request("GET", "/api/versions/00000000-0000-0000-0000-000000000000", { token });
      expect(res.status).toBe(404);
    });
  });

  describe("Version deduplication", () => {
    it("should skip saving when content unchanged", async () => {
      await versionService.saveVersion("skill", "dedup", "same content", "init");
      await versionService.saveVersion("skill", "dedup", "same content", "manual");

      const res = await request("GET", "/api/versions?entityType=skill&entityId=dedup", { token });
      const data = await json<unknown[]>(res);
      expect(data).toHaveLength(1); // deduped
    });
  });
});
