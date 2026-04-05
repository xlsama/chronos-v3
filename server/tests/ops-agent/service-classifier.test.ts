import { describe, it, expect } from "vitest";
import { classifyServiceOperation } from "@/ops-agent/safety/service-classifier";

describe("ServiceSafety Classifier", () => {
  // ── Docker ──────────────────────────────────────────

  describe("docker", () => {
    it.each([
      ["listContainers", "read"],
      ["inspectContainer", "read"],
      ["containerLogs", "read"],
      ["containerTop", "read"],
      ["containerStats", "read"],
      ["listImages", "read"],
      ["listNetworks", "read"],
      ["listVolumes", "read"],
      ["systemInfo", "read"],
      ["systemDf", "read"],
    ] as const)("%s → %s", (op, expected) => {
      expect(classifyServiceOperation("docker", op)).toBe(expected);
    });

    it.each([
      ["startContainer", "write"],
      ["stopContainer", "write"],
      ["restartContainer", "write"],
      ["pauseContainer", "write"],
      ["unpauseContainer", "write"],
      ["pullImage", "write"],
    ] as const)("%s → %s", (op, expected) => {
      expect(classifyServiceOperation("docker", op)).toBe(expected);
    });

    it.each([
      ["removeContainer", "dangerous"],
      ["removeImage", "dangerous"],
      ["killContainer", "dangerous"],
    ] as const)("%s → %s", (op, expected) => {
      expect(classifyServiceOperation("docker", op)).toBe(expected);
    });
  });

  // ── Kubernetes ──────────────────────────────────────

  describe("kubernetes", () => {
    it.each([
      ["listNamespaces", "read"],
      ["listPods", "read"],
      ["describePod", "read"],
      ["getPodLogs", "read"],
      ["listDeployments", "read"],
      ["describeDeployment", "read"],
      ["listServices", "read"],
      ["listNodes", "read"],
    ] as const)("%s → %s", (op, expected) => {
      expect(classifyServiceOperation("kubernetes", op)).toBe(expected);
    });

    it.each([
      ["scaleDeployment", "write"],
      ["restartDeployment", "write"],
    ] as const)("%s → %s", (op, expected) => {
      expect(classifyServiceOperation("kubernetes", op)).toBe(expected);
    });

    it("deletePod → dangerous", () => {
      expect(classifyServiceOperation("kubernetes", "deletePod")).toBe("dangerous");
    });
  });

  // ── MongoDB ─────────────────────────────────────────

  describe("mongodb", () => {
    it.each([
      ["listDatabases", "read"],
      ["listCollections", "read"],
      ["findDocuments", "read"],
      ["countDocuments", "read"],
      ["aggregate", "read"],
    ] as const)("%s → %s", (op, expected) => {
      expect(classifyServiceOperation("mongodb", op)).toBe(expected);
    });

    it.each([
      ["insertOne", "write"],
      ["updateMany", "write"],
    ] as const)("%s → %s", (op, expected) => {
      expect(classifyServiceOperation("mongodb", op)).toBe(expected);
    });

    it("deleteMany → dangerous", () => {
      expect(classifyServiceOperation("mongodb", "deleteMany")).toBe("dangerous");
    });
  });

  // ── PostgreSQL — executeSql ─────────────────────────

  describe("postgresql — executeSql", () => {
    it.each([
      ["SELECT * FROM users", "read"],
      ["select count(*) from orders", "read"],
      ["SHOW TABLES", "read"],
      ["DESCRIBE users", "read"],
      ["DESC users", "read"],
      ["EXPLAIN SELECT * FROM users", "read"],
      ["WITH cte AS (SELECT 1) SELECT * FROM cte", "read"],
      ["  SELECT * FROM users", "read"], // 前导空格
    ] as const)("SQL: %s → %s", (sql, expected) => {
      expect(classifyServiceOperation("postgresql", "executeSql", { query: sql })).toBe(expected);
    });

    it.each([
      ["INSERT INTO users (name) VALUES ('test')", "write"],
      ["UPDATE users SET name = 'test' WHERE id = 1", "write"],
      ["CREATE TABLE test (id int)", "write"],
      ["ALTER TABLE users ADD COLUMN email text", "write"],
      ["GRANT SELECT ON users TO reader", "write"],
      ["REVOKE ALL ON users FROM reader", "write"],
    ] as const)("SQL: %s → %s", (sql, expected) => {
      expect(classifyServiceOperation("postgresql", "executeSql", { query: sql })).toBe(expected);
    });

    it.each([
      ["DELETE FROM users WHERE id = 1", "dangerous"],
      ["DROP TABLE users", "dangerous"],
      ["DROP INDEX idx_users_name", "dangerous"],
      ["ALTER TABLE users DROP COLUMN email", "dangerous"],
    ] as const)("SQL: %s → %s", (sql, expected) => {
      expect(classifyServiceOperation("postgresql", "executeSql", { query: sql })).toBe(expected);
    });

    it.each([
      ["DROP DATABASE production", "blocked"],
      ["TRUNCATE TABLE users", "blocked"],
      ["DROP SCHEMA public CASCADE", "blocked"],
    ] as const)("SQL: %s → %s", (sql, expected) => {
      expect(classifyServiceOperation("postgresql", "executeSql", { query: sql })).toBe(expected);
    });

    it("空 SQL → read", () => {
      expect(classifyServiceOperation("postgresql", "executeSql", { query: "" })).toBe("read");
    });

    it("未知 SQL → write (fail-closed)", () => {
      expect(classifyServiceOperation("postgresql", "executeSql", { query: "VACUUM ANALYZE" })).toBe("write");
    });
  });

  // ── MySQL — executeSql ──────────────────────────────

  describe("mysql — executeSql", () => {
    it("SELECT → read", () => {
      expect(classifyServiceOperation("mysql", "executeSql", { query: "SELECT 1" })).toBe("read");
    });

    it("INSERT → write", () => {
      expect(
        classifyServiceOperation("mysql", "executeSql", { query: "INSERT INTO t VALUES (1)" }),
      ).toBe("write");
    });

    it("DELETE FROM → dangerous", () => {
      expect(
        classifyServiceOperation("mysql", "executeSql", { query: "DELETE FROM users WHERE id=1" }),
      ).toBe("dangerous");
    });

    it("DROP DATABASE → blocked", () => {
      expect(
        classifyServiceOperation("mysql", "executeSql", { query: "DROP DATABASE test" }),
      ).toBe("blocked");
    });
  });

  // ── PostgreSQL/MySQL — 非 SQL 操作 ──────────────────

  describe("postgresql/mysql — read operations", () => {
    it.each([
      ["postgresql", "listDatabases"],
      ["postgresql", "listTables"],
      ["postgresql", "describeTable"],
      ["postgresql", "tableRowCount"],
      ["mysql", "listDatabases"],
      ["mysql", "listTables"],
      ["mysql", "describeTable"],
      ["mysql", "tableRowCount"],
    ] as const)("%s.%s → read", (svc, op) => {
      expect(classifyServiceOperation(svc, op)).toBe("read");
    });
  });

  // ── Fail-closed 默认 ───────────────────────────────

  describe("fail-closed defaults", () => {
    it("未知 serviceType → write", () => {
      expect(classifyServiceOperation("redis", "get")).toBe("write");
    });

    it("未知 operation → write", () => {
      expect(classifyServiceOperation("docker", "nonExistentOp")).toBe("write");
    });

    it("空 serviceType → write", () => {
      expect(classifyServiceOperation("", "listContainers")).toBe("write");
    });
  });

  // ── 多语句 SQL ─────────────────────────────────────

  describe("multi-statement SQL", () => {
    it("SELECT 1; DROP TABLE users → dangerous (DROP TABLE 匹配)", () => {
      expect(
        classifyServiceOperation("postgresql", "executeSql", {
          query: "SELECT 1; DROP TABLE users",
        }),
      ).toBe("dangerous");
    });

    it("SELECT 1; DELETE FROM users → dangerous", () => {
      expect(
        classifyServiceOperation("postgresql", "executeSql", {
          query: "SELECT 1; DELETE FROM users WHERE 1=1",
        }),
      ).toBe("dangerous");
    });
  });
});
