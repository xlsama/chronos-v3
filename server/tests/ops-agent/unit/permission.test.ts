import { describe, it, expect } from "vitest";
import { serviceExecTool } from "@/ops-agent/tools/service-exec";

const check = (operation: string) =>
  serviceExecTool.checkPermission!({
    serviceId: "test-svc",
    operation,
    parameters: {},
  });

describe("serviceExecTool.checkPermission", () => {
  describe("安全操作 → allow", () => {
    it.each([
      "listContainers",
      "inspectContainer",
      "containerLogs",
      "containerTop",
      "containerStats",
      "listImages",
      "listNetworks",
      "listVolumes",
      "systemInfo",
      "listPods",
      "describePod",
      "getPodLogs",
      "listDeployments",
      "listServices",
      "listNodes",
      "executeSql",
      "listDatabases",
      "listTables",
      "describeTable",
      "findDocuments",
      "countDocuments",
      "aggregate",
    ])("%s → allow", async (operation) => {
      const result = await check(operation);
      expect(result.behavior).toBe("allow");
    });
  });

  describe("危险操作 → ask", () => {
    it.each([
      ["deleteContainer", "delete"],
      ["removeContainer", "remove"],
      ["removeImage", "remove"],
      ["killContainer", "kill"],
      ["restartContainer", "restart"],
      ["restartDeployment", "restart"],
      ["stopContainer", "stop"],
      ["dropDatabase", "drop"],
      ["truncateTable", "truncate"],
      ["pruneImages", "prune"],
      ["drainNode", "drain"],
    ])("%s (含 %s) → ask", async (operation) => {
      const result = await check(operation);
      expect(result.behavior).toBe("ask");
      expect(result.riskLevel).toBe("HIGH");
      expect(result.reason).toContain(operation);
    });
  });

  it("大小写不敏感: DeleteContainer → ask", async () => {
    const result = await check("DeleteContainer");
    expect(result.behavior).toBe("ask");
  });

  it("包含匹配: forceRemoveImage → ask", async () => {
    const result = await check("forceRemoveImage");
    expect(result.behavior).toBe("ask");
  });

  it("deleteMany (MongoDB) → ask", async () => {
    const result = await check("deleteMany");
    expect(result.behavior).toBe("ask");
  });

  it("updateMany 不触发 (不含危险词) → allow", async () => {
    const result = await check("updateMany");
    expect(result.behavior).toBe("allow");
  });

  it("insertOne 不触发 → allow", async () => {
    const result = await check("insertOne");
    expect(result.behavior).toBe("allow");
  });

  it("scaleDeployment 不触发 → allow", async () => {
    const result = await check("scaleDeployment");
    expect(result.behavior).toBe("allow");
  });

  // 边界验证: "stop" 是否会误匹配包含 "stop" 子串的操作
  it("containerStats 不包含 stop → allow", async () => {
    // "stop" 不是 "stats" 的子串，但 "listContainerStats" 也不包含 "stop"
    const result = await check("containerStats");
    expect(result.behavior).toBe("allow");
  });
});
