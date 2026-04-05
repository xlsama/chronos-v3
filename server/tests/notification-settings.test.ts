import { describe, it, expect, beforeEach } from "bun:test";
import { request, json, registerAndLogin } from "./helpers";

describe("Notification Settings API", () => {
  let token: string;

  beforeEach(async () => {
    token = await registerAndLogin();
  });

  describe("GET /api/notification-settings/:platform", () => {
    it("should return null when no settings exist", async () => {
      const res = await request("GET", "/api/notification-settings/feishu", { token });
      expect(res.status).toBe(200);
      const data = await res.json();
      expect(data).toBeNull();
    });
  });

  describe("PUT /api/notification-settings/:platform", () => {
    it("should create notification settings", async () => {
      const res = await request("PUT", "/api/notification-settings/feishu", {
        token,
        body: { webhookUrl: "https://hook.example.com/abc", enabled: true },
      });
      expect(res.status).toBe(200);
      const data = await json<{ platform: string; webhookUrl: string; enabled: boolean }>(res);
      expect(data.platform).toBe("feishu");
      expect(data.webhookUrl).toBe("https://hook.example.com/abc");
      expect(data.enabled).toBe(true);
    });

    it("should update existing settings", async () => {
      await request("PUT", "/api/notification-settings/feishu", {
        token,
        body: { webhookUrl: "https://old.example.com", enabled: true },
      });

      const res = await request("PUT", "/api/notification-settings/feishu", {
        token,
        body: { webhookUrl: "https://new.example.com", signKey: "secret123", enabled: false },
      });
      const data = await json<{ webhookUrl: string; signKey: string | null; enabled: boolean }>(res);
      expect(data.webhookUrl).toBe("https://new.example.com");
      expect(data.signKey).toBe("secret123");
      expect(data.enabled).toBe(false);
    });

    it("should encrypt and decrypt webhook url correctly", async () => {
      await request("PUT", "/api/notification-settings/feishu", {
        token,
        body: { webhookUrl: "https://hook.example.com/secret", enabled: true },
      });

      const getRes = await request("GET", "/api/notification-settings/feishu", { token });
      const data = await json<{ webhookUrl: string }>(getRes);
      expect(data.webhookUrl).toBe("https://hook.example.com/secret");
    });
  });
});
