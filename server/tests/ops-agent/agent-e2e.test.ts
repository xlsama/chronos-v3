import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import Docker from "dockerode";
import { db } from "@/db/connection";
import { incidents, services, agentSessions } from "@/db/schema";
import { eq } from "drizzle-orm";
import { request, json, registerAndLogin } from "../helpers";

const DOCKER_SOCKET = "/var/run/docker.sock";
const TEST_CONTAINER_NAME = "chronos-test-nginx";
const TEST_CONTAINER_PORT = "18080";

function parseSSEEvents(raw: string) {
  return raw
    .split("\n\n")
    .filter((block) => block.includes("event:"))
    .map((block) => {
      const eventMatch = block.match(/event:\s*(.+)/);
      const dataMatch = block.match(/data:\s*(.+)/);
      let data = {};
      if (dataMatch?.[1]) {
        try {
          data = JSON.parse(dataMatch[1]);
        } catch {
          data = { raw: dataMatch[1] };
        }
      }
      return {
        type: eventMatch?.[1]?.trim() || "",
        data: data as Record<string, unknown>,
      };
    });
}

describe("Ops Agent E2E — Docker", () => {
  let token: string;
  let incidentId: string;
  let dockerServiceId: string;
  const docker = new Docker({ socketPath: DOCKER_SOCKET });

  beforeEach(async () => {
    // 1. 注册登录
    token = await registerAndLogin();

    // 2. 创建 Docker service（本地 socket）
    const [svc] = await db
      .insert(services)
      .values({
        name: "local-docker",
        serviceType: "docker",
        host: "localhost",
        port: 2376,
        config: { socketPath: DOCKER_SOCKET },
      })
      .returning();
    dockerServiceId = svc.id;

    // 3. 启动测试容器 nginx
    // 清理旧容器（如果存在）
    try {
      const old = docker.getContainer(TEST_CONTAINER_NAME);
      await old.stop().catch(() => {});
      await old.remove().catch(() => {});
    } catch {
      // container doesn't exist
    }

    // 创建测试容器（需要先 docker pull nginx:alpine）
    const container = await docker.createContainer({
      Image: "nginx:alpine",
      name: TEST_CONTAINER_NAME,
      HostConfig: {
        PortBindings: { "80/tcp": [{ HostPort: TEST_CONTAINER_PORT }] },
      },
    });
    await container.start();

    // 4. 创建 incident
    const [inc] = await db
      .insert(incidents)
      .values({
        description: "测试: nginx 容器状态检查",
        severity: "P3",
      })
      .returning();
    incidentId = inc.id;
  });

  afterEach(async () => {
    // 清理测试容器
    try {
      const c = docker.getContainer(TEST_CONTAINER_NAME);
      await c.stop().catch(() => {});
      await c.remove().catch(() => {});
    } catch {
      // ignore
    }
  });

  it("Agent 应能查询 Docker 容器并返回总结", async () => {
    const prompt = [
      `请检查 Docker 服务（service ID: ${dockerServiceId}）中的容器运行状态，`,
      `特别关注名为 ${TEST_CONTAINER_NAME} 的容器是否正常运行。`,
    ].join("");

    // 触发 Agent
    const res = await request("POST", `/api/agent/${incidentId}/run`, {
      token,
      body: { prompt },
    });

    expect(res.status).toBe(200);

    // 读取完整 SSE 流
    const text = await res.text();
    const events = parseSSEEvents(text);

    console.log("\n========== SSE EVENTS ==========");
    for (const ev of events) {
      console.log(`  [${ev.type}] ${JSON.stringify(ev.data).slice(0, 120)}`);
    }
    console.log("========== END EVENTS ==========\n");

    // 验证关键事件存在
    expect(events.some((e) => e.type === "session_started")).toBe(true);
    expect(events.some((e) => e.type === "tool_start")).toBe(true);
    expect(events.some((e) => e.type === "tool_result")).toBe(true);
    expect(events.some((e) => e.type === "done")).toBe(true);

    // 验证 tool_result 包含容器名
    const toolResults = events.filter((e) => e.type === "tool_result");
    const hasNginx = toolResults.some((e) => {
      const output = (e.data as { output?: string }).output || "";
      return output.includes(TEST_CONTAINER_NAME);
    });
    expect(hasNginx).toBe(true);

    // 验证 DB 状态
    const [session] = await db
      .select()
      .from(agentSessions)
      .where(eq(agentSessions.incidentId, incidentId))
      .limit(1);

    expect(session).toBeDefined();
    expect(session.status).toBe("completed");
    expect(session.summary).toBeTruthy();
    expect(session.turnCount).toBeGreaterThan(0);

    console.log(`\n========== FINAL STATE ==========`);
    console.log(`  status: ${session.status}`);
    console.log(`  turns: ${session.turnCount}`);
    console.log(`  summary: ${(session.summary || "").slice(0, 200)}...`);
    console.log(`  messages: ${(session.agentMessages as unknown[]).length}`);
    console.log(`========== END STATE ==========\n`);
  }, 120_000); // LLM 调用可能较慢，120s 超时
});
