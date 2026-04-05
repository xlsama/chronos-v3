import { describe, it, expect } from "bun:test";
import { request, json, registerAndLogin } from "./helpers";

describe("Auth API", () => {
  describe("POST /api/auth/register", () => {
    it("should register a new user", async () => {
      const res = await request("POST", "/api/auth/register", {
        body: { email: "new@test.com", password: "123456", name: "New User" },
      });
      expect(res.status).toBe(201);
      const data = await json<{ id: string; email: string; name: string; isActive: boolean }>(res);
      expect(data.email).toBe("new@test.com");
      expect(data.name).toBe("New User");
      expect(data.isActive).toBe(true);
      expect(data.id).toBeDefined();
    });

    it("should reject duplicate email", async () => {
      await request("POST", "/api/auth/register", {
        body: { email: "dup@test.com", password: "123456", name: "User" },
      });
      const res = await request("POST", "/api/auth/register", {
        body: { email: "dup@test.com", password: "123456", name: "User 2" },
      });
      expect(res.status).toBe(409);
    });

    it("should reject short password", async () => {
      const res = await request("POST", "/api/auth/register", {
        body: { email: "short@test.com", password: "123", name: "User" },
      });
      expect(res.status).toBe(400);
    });

    it("should reject invalid email", async () => {
      const res = await request("POST", "/api/auth/register", {
        body: { email: "not-email", password: "123456", name: "User" },
      });
      expect(res.status).toBe(400);
    });
  });

  describe("POST /api/auth/login", () => {
    it("should login and return token", async () => {
      await request("POST", "/api/auth/register", {
        body: { email: "login@test.com", password: "123456", name: "User" },
      });
      const res = await request("POST", "/api/auth/login", {
        body: { email: "login@test.com", password: "123456" },
      });
      expect(res.status).toBe(200);
      const data = await json<{ accessToken: string; tokenType: string }>(res);
      expect(data.accessToken).toBeDefined();
      expect(data.tokenType).toBe("bearer");
    });

    it("should reject wrong password", async () => {
      await request("POST", "/api/auth/register", {
        body: { email: "wrong@test.com", password: "123456", name: "User" },
      });
      const res = await request("POST", "/api/auth/login", {
        body: { email: "wrong@test.com", password: "wrong" },
      });
      expect(res.status).toBe(401);
    });

    it("should reject non-existent email", async () => {
      const res = await request("POST", "/api/auth/login", {
        body: { email: "none@test.com", password: "123456" },
      });
      expect(res.status).toBe(401);
    });
  });

  describe("GET /api/auth/me", () => {
    it("should return current user", async () => {
      const token = await registerAndLogin();
      const res = await request("GET", "/api/auth/me", { token });
      expect(res.status).toBe(200);
      const data = await json<{ email: string; name: string }>(res);
      expect(data.email).toBe("test@test.com");
      expect(data.name).toBe("Test User");
    });

    it("should reject without token", async () => {
      const res = await request("GET", "/api/auth/me");
      expect(res.status).toBe(401);
    });

    it("should reject invalid token", async () => {
      const res = await request("GET", "/api/auth/me", { token: "bad-token" });
      expect(res.status).toBe(401);
    });
  });

  describe("PUT /api/auth/password", () => {
    it("should change password", async () => {
      const token = await registerAndLogin("pw@test.com", "oldpass");
      const res = await request("PUT", "/api/auth/password", {
        token,
        body: { oldPassword: "oldpass", newPassword: "newpass" },
      });
      expect(res.status).toBe(200);

      // Login with new password
      const loginRes = await request("POST", "/api/auth/login", {
        body: { email: "pw@test.com", password: "newpass" },
      });
      expect(loginRes.status).toBe(200);
    });

    it("should reject wrong old password", async () => {
      const token = await registerAndLogin("pw2@test.com", "oldpass");
      const res = await request("PUT", "/api/auth/password", {
        token,
        body: { oldPassword: "wrong", newPassword: "newpass" },
      });
      expect(res.status).toBe(401);
    });
  });
});
