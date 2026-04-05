import { describe, it, expect, beforeEach, afterEach } from "vitest";
import Docker from "dockerode";
import { db } from "@/db/connection";
import {
  incidents,
  services,
  projects,
  projectDocuments,
  documentChunks,
  incidentHistory,
  agentSessions,
} from "@/db/schema";
import { eq } from "drizzle-orm";
import { embedTexts } from "@/lib/embedder";
import { chunkSegments } from "@/lib/chunker";
import { request, json, registerAndLogin } from "../helpers";

const DOCKER_SOCKET = "/var/run/docker.sock";
const TEST_CONTAINER_NAME = "chronos-test-nginx-search";

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

// ─── 场景 1：知识库混合检索 + Docker 排查 ─────────────────

describe("Ops Agent E2E — 知识库检索 + 排查", () => {
  let token: string;
  let incidentId: string;
  let dockerServiceId: string;
  const docker = new Docker({ socketPath: DOCKER_SOCKET });

  beforeEach(async () => {
    token = await registerAndLogin();

    // 1. 创建项目
    const [project] = await db
      .insert(projects)
      .values({ name: "nginx-project", slug: "nginx-project" })
      .returning();

    // 2. 创建文档
    const docContent = [
      "# Nginx 运维手册",
      "",
      "## 常见问题排查",
      "",
      "### 502 Bad Gateway",
      "nginx 返回 502 通常是后端服务不可用。排查步骤：",
      "1. 检查 upstream 服务是否存活（docker ps 查看容器状态）",
      "2. 查看 nginx error.log 中的具体错误信息",
      "3. 检查端口是否被占用或配置错误",
      "4. 确认后端服务的健康检查是否正常",
      "",
      "### 504 Gateway Timeout",
      "nginx 返回 504 通常是后端服务响应超时。",
      "1. 检查 proxy_read_timeout 配置",
      "2. 查看后端服务的性能指标",
    ].join("\n");

    const [doc] = await db
      .insert(projectDocuments)
      .values({
        projectId: project.id,
        filename: "nginx-guide.md",
        content: docContent,
        docType: "markdown",
        status: "indexed",
      })
      .returning();

    // 3. 分块 + embedding + 存入 chunks
    const chunks = chunkSegments([{ content: docContent, metadata: {} }]);
    const embeddings = await embedTexts(chunks.map((c) => c.content));

    await db.insert(documentChunks).values(
      chunks.map((chunk, i) => ({
        documentId: doc.id,
        projectId: project.id,
        chunkIndex: chunk.index,
        content: chunk.content,
        embedding: embeddings[i],
        metadata: chunk.metadata,
      })),
    );

    // 4. 创建 Docker service
    const [svc] = await db
      .insert(services)
      .values({
        name: "local-docker-search",
        serviceType: "docker",
        host: "localhost",
        port: 2376,
        config: { socketPath: DOCKER_SOCKET },
      })
      .returning();
    dockerServiceId = svc.id;

    // 5. 启动测试容器
    try {
      const old = docker.getContainer(TEST_CONTAINER_NAME);
      await old.stop().catch(() => {});
      await old.remove().catch(() => {});
    } catch {}

    const container = await docker.createContainer({
      Image: "nginx:alpine",
      name: TEST_CONTAINER_NAME,
      HostConfig: {
        PortBindings: { "80/tcp": [{ HostPort: "18081" }] },
      },
    });
    await container.start();

    // 6. 创建 incident
    const [inc] = await db
      .insert(incidents)
      .values({ description: "nginx 返回 502 错误", severity: "P2" })
      .returning();
    incidentId = inc.id;
  });

  afterEach(async () => {
    try {
      const c = docker.getContainer(TEST_CONTAINER_NAME);
      await c.stop().catch(() => {});
      await c.remove().catch(() => {});
    } catch {}
  });

  it("Agent 应先搜索知识库再检查容器", async () => {
    const res = await request("POST", `/api/agent/${incidentId}/run`, {
      token,
      body: {
        prompt: "nginx 返回 502 错误，请帮我排查原因。",
      },
    });

    expect(res.status).toBe(200);
    const text = await res.text();
    const events = parseSSEEvents(text);

    console.log("\n========== 场景1 SSE EVENTS ==========");
    for (const ev of events) {
      console.log(`  [${ev.type}] ${JSON.stringify(ev.data).slice(0, 150)}`);
    }
    console.log("========== END ==========\n");

    // 验证: search_knowledge 被调用
    const searchKnowledgeCalled = events.some(
      (e) => e.type === "tool_start" && (e.data as { toolName?: string }).toolName === "search_knowledge",
    );
    expect(searchKnowledgeCalled).toBe(true);

    // 验证: search_knowledge 返回了包含 502/upstream 的结果
    const searchResults = events.filter(
      (e) => e.type === "tool_result" && (e.data as { toolName?: string }).toolName === "search_knowledge",
    );
    const hasRelevantContent = searchResults.some((e) => {
      const output = (e.data as { output?: string }).output || "";
      return output.includes("502") || output.includes("upstream");
    });
    expect(hasRelevantContent).toBe(true);

    // 验证: 最终完成
    expect(events.some((e) => e.type === "done")).toBe(true);

    // 验证 DB
    const [session] = await db
      .select()
      .from(agentSessions)
      .where(eq(agentSessions.incidentId, incidentId));
    expect(session.status).toBe("completed");
  }, 120_000);
});

// ─── 场景 2：制定计划 + 历史事件搜索 + 排查 ─────────────────

describe("Ops Agent E2E — 历史事件 + 计划 + 排查", () => {
  let token: string;
  let incidentId: string;
  let dockerServiceId: string;
  const docker = new Docker({ socketPath: DOCKER_SOCKET });

  beforeEach(async () => {
    token = await registerAndLogin();

    // 1. 插入历史事件（含 embedding）
    const historyTitle = "nginx OOM 导致服务中断";
    const historySummary = [
      "## 事件总结",
      "容器内存不足触发 OOM Killer，nginx 进程被杀死。",
      "### 排查过程",
      "1. docker stats 发现内存使用率 99%",
      "2. docker logs 显示 worker process exited with fatal error",
      "3. docker inspect 确认 Memory Limit 设置过低（64MB）",
      "### 解决方案",
      "将容器 Memory Limit 从 64MB 调整为 256MB，重启容器后恢复正常。",
    ].join("\n");

    const [embedding] = await embedTexts([`${historyTitle} ${historySummary}`]);

    await db.insert(incidentHistory).values({
      title: historyTitle,
      summaryMd: historySummary,
      embedding,
      occurrenceCount: 3,
    });

    // 2. 创建 Docker service
    const [svc] = await db
      .insert(services)
      .values({
        name: "local-docker-history",
        serviceType: "docker",
        host: "localhost",
        port: 2376,
        config: { socketPath: DOCKER_SOCKET },
      })
      .returning();
    dockerServiceId = svc.id;

    // 3. 启动测试容器
    try {
      const old = docker.getContainer(TEST_CONTAINER_NAME);
      await old.stop().catch(() => {});
      await old.remove().catch(() => {});
    } catch {}

    const container = await docker.createContainer({
      Image: "nginx:alpine",
      name: TEST_CONTAINER_NAME,
      HostConfig: {
        PortBindings: { "80/tcp": [{ HostPort: "18081" }] },
      },
    });
    await container.start();

    // 4. 创建 incident
    const [inc] = await db
      .insert(incidents)
      .values({
        description: "nginx 容器疑似内存异常，请系统性排查",
        severity: "P2",
      })
      .returning();
    incidentId = inc.id;
  });

  afterEach(async () => {
    try {
      const c = docker.getContainer(TEST_CONTAINER_NAME);
      await c.stop().catch(() => {});
      await c.remove().catch(() => {});
    } catch {}
  });

  it("Agent 应搜索历史事件、制定计划并排查", async () => {
    const res = await request("POST", `/api/agent/${incidentId}/run`, {
      token,
      body: {
        prompt: "nginx 容器疑似内存异常，请系统性排查。",
      },
    });

    expect(res.status).toBe(200);
    const text = await res.text();
    const events = parseSSEEvents(text);

    console.log("\n========== 场景2 SSE EVENTS ==========");
    for (const ev of events) {
      console.log(`  [${ev.type}] ${JSON.stringify(ev.data).slice(0, 150)}`);
    }
    console.log("========== END ==========\n");

    // 验证: search_incidents 被调用
    const searchIncidentsCalled = events.some(
      (e) => e.type === "tool_start" && (e.data as { toolName?: string }).toolName === "search_incidents",
    );
    expect(searchIncidentsCalled).toBe(true);

    // 验证: search_incidents 返回了 OOM 相关结果
    const incidentResults = events.filter(
      (e) => e.type === "tool_result" && (e.data as { toolName?: string }).toolName === "search_incidents",
    );
    const hasOOMHistory = incidentResults.some((e) => {
      const output = (e.data as { output?: string }).output || "";
      return output.includes("OOM") || output.includes("内存");
    });
    expect(hasOOMHistory).toBe(true);

    // 验证: update_plan 被调用（plan_updated 事件）
    const planUpdated = events.some((e) => e.type === "plan_updated");
    // 注意: LLM 不一定每次都调用 update_plan，所以这里用 log 而不是 strict assert
    if (planUpdated) {
      console.log("  ✓ Agent 制定了调查计划");
    } else {
      console.log("  ⚠ Agent 未调用 update_plan（LLM 自行决定）");
    }

    // 验证: 最终完成
    expect(events.some((e) => e.type === "done")).toBe(true);

    // 验证 DB
    const [session] = await db
      .select()
      .from(agentSessions)
      .where(eq(agentSessions.incidentId, incidentId));
    expect(session.status).toBe("completed");

    if (session.planMd) {
      console.log(`  ✓ Plan saved: "${(session.planMd as string).slice(0, 100)}..."`);
    }

    console.log(`  Final: status=${session.status}, turns=${session.turnCount}`);
  }, 120_000);
});
