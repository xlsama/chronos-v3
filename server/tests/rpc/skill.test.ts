import { describe, it, expect, beforeEach } from "bun:test";
import { rm, mkdir } from "fs/promises";
import { request, registerAndLogin } from "../helpers";
import { skillsDir } from "@/lib/paths";

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

describe("Skill RPC", () => {
  let token: string;

  beforeEach(async () => {
    token = await registerAndLogin();
    try {
      await rm(skillsDir(), { recursive: true, force: true });
    } catch {}
    await mkdir(skillsDir(), { recursive: true });
  });

  describe("skill.create", () => {
    it("should create a skill", async () => {
      const res = await rpc("skill.create", { slug: "test-skill" }, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<{ slug: string; name: string; draft: boolean }>(res);
      expect(data.slug).toBe("test-skill");
      expect(data.draft).toBe(true);
    });

    it("should reject duplicate slug", async () => {
      await rpc("skill.create", { slug: "dup-skill" }, token);
      const res = await rpc("skill.create", { slug: "dup-skill" }, token);
      expect(res.status).toBe(409);
    });

    it("should reject invalid slug", async () => {
      const res = await rpc("skill.create", { slug: "INVALID!" }, token);
      expect(res.status).toBe(400);
    });
  });

  describe("skill.list", () => {
    it("should list skills", async () => {
      await rpc("skill.create", { slug: "skill-a" }, token);
      await rpc("skill.create", { slug: "skill-b" }, token);

      const res = await rpc("skill.list", {}, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<Array<{ slug: string }>>(res);
      expect(data).toHaveLength(2);
    });

    it("should return empty array when no skills", async () => {
      const res = await rpc("skill.list", {}, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<unknown[]>(res);
      expect(data).toHaveLength(0);
    });
  });

  describe("skill.get", () => {
    it("should return skill detail with content", async () => {
      await rpc("skill.create", { slug: "detail-skill" }, token);

      const res = await rpc("skill.get", { slug: "detail-skill" }, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<{
        slug: string;
        content: string;
        scriptFiles: string[];
        referenceFiles: string[];
        assetFiles: string[];
      }>(res);
      expect(data.slug).toBe("detail-skill");
      expect(data.content).toBeDefined();
      expect(data.scriptFiles).toEqual([]);
      expect(data.referenceFiles).toEqual([]);
      expect(data.assetFiles).toEqual([]);
    });

    it("should return 404 for non-existent skill", async () => {
      const res = await rpc("skill.get", { slug: "nope" }, token);
      expect(res.status).toBe(404);
    });
  });

  describe("skill.update", () => {
    it("should update skill content", async () => {
      await rpc("skill.create", { slug: "update-skill" }, token);

      const newContent = "---\nname: Updated\ndescription: Updated desc\n---\n\nNew body";
      const res = await rpc("skill.update", { slug: "update-skill", content: newContent }, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<{ name: string; description: string }>(res);
      expect(data.name).toBe("Updated");
      expect(data.description).toBe("Updated desc");
    });

    it("should return 404 for non-existent skill", async () => {
      const res = await rpc("skill.update", { slug: "nope", content: "anything" }, token);
      expect(res.status).toBe(404);
    });
  });

  describe("skill.remove", () => {
    it("should delete a skill", async () => {
      await rpc("skill.create", { slug: "del-skill" }, token);

      const res = await rpc("skill.remove", { slug: "del-skill" }, token);
      expect(res.status).toBe(200);
      const data = await rpcJson<{ ok: boolean }>(res);
      expect(data.ok).toBe(true);

      const getRes = await rpc("skill.get", { slug: "del-skill" }, token);
      expect(getRes.status).toBe(404);
    });

    it("should return 404 for non-existent skill", async () => {
      const res = await rpc("skill.remove", { slug: "nope" }, token);
      expect(res.status).toBe(404);
    });
  });

  describe("skill.putFile / skill.getFile / skill.deleteFile", () => {
    it("should write and read a script file", async () => {
      await rpc("skill.create", { slug: "file-skill" }, token);

      const writeRes = await rpc(
        "skill.putFile",
        { slug: "file-skill", path: "scripts/run.sh", content: "#!/bin/bash\necho hello" },
        token,
      );
      expect(writeRes.status).toBe(200);

      const readRes = await rpc(
        "skill.getFile",
        { slug: "file-skill", path: "scripts/run.sh" },
        token,
      );
      expect(readRes.status).toBe(200);
      const data = await rpcJson<{ content: string }>(readRes);
      expect(data.content).toContain("echo hello");
    });

    it("should delete a file", async () => {
      await rpc("skill.create", { slug: "del-file-skill" }, token);
      await rpc(
        "skill.putFile",
        { slug: "del-file-skill", path: "scripts/tmp.sh", content: "temp" },
        token,
      );

      const res = await rpc(
        "skill.deleteFile",
        { slug: "del-file-skill", path: "scripts/tmp.sh" },
        token,
      );
      expect(res.status).toBe(200);

      const getRes = await rpc(
        "skill.getFile",
        { slug: "del-file-skill", path: "scripts/tmp.sh" },
        token,
      );
      expect(getRes.status).toBe(404);
    });

    it("should reject path traversal", async () => {
      await rpc("skill.create", { slug: "traversal-skill" }, token);

      const res = await rpc(
        "skill.putFile",
        { slug: "traversal-skill", path: "../etc/passwd", content: "hack" },
        token,
      );
      expect(res.status).toBe(400);
    });

    it("should reject paths outside allowed subdirs", async () => {
      await rpc("skill.create", { slug: "badpath-skill" }, token);

      const res = await rpc(
        "skill.putFile",
        { slug: "badpath-skill", path: "notallowed/file.txt", content: "nope" },
        token,
      );
      expect(res.status).toBe(400);
    });

    it("should show files in skill detail after creation", async () => {
      await rpc("skill.create", { slug: "files-detail" }, token);
      await rpc(
        "skill.putFile",
        { slug: "files-detail", path: "scripts/check.sh", content: "#!/bin/bash" },
        token,
      );
      await rpc(
        "skill.putFile",
        { slug: "files-detail", path: "references/guide.md", content: "# Guide" },
        token,
      );

      const res = await rpc("skill.get", { slug: "files-detail" }, token);
      const data = await rpcJson<{
        scriptFiles: string[];
        referenceFiles: string[];
        hasScripts: boolean;
        hasReferences: boolean;
      }>(res);
      expect(data.scriptFiles).toContain("check.sh");
      expect(data.referenceFiles).toContain("guide.md");
      expect(data.hasScripts).toBe(true);
      expect(data.hasReferences).toBe(true);
    });
  });

  describe("auth", () => {
    it("should reject unauthenticated requests", async () => {
      const res = await rpc("skill.list", {});
      expect(res.status).toBe(401);
    });
  });
});
