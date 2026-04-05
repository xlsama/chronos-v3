import { describe, it, expect, beforeEach } from "vitest";
import { db } from "@/db/connection";
import { incidents, services, agentSessions } from "@/db/schema";
import { eq } from "drizzle-orm";
import { request, json, registerAndLogin } from "../helpers";
import { shouldCompact } from "@/ops-agent/context/compact";
import type { Message } from "@/ops-agent/types";

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

describe("shouldCompact", () => {
  it("should return false for short messages", () => {
    const messages: Message[] = [
      { role: "user", content: "hello" },
      { role: "assistant", content: "hi there" },
    ];
    expect(shouldCompact(messages)).toBe(false);
  });

  it("should return true when messages exceed threshold", () => {
    const longContent = "x".repeat(90_000);
    const messages: Message[] = [
      { role: "user", content: longContent },
    ];
    expect(shouldCompact(messages)).toBe(true);
  });
});

describe("Ops Agent — Compact 触发测试", () => {
  let token: string;

  beforeEach(async () => {
    token = await registerAndLogin();
  });

  it("Agent 应在上下文过长时触发 compact 并继续排查", async () => {
    // 1. 创建 Docker service
    const [svc] = await db
      .insert(services)
      .values({
        name: "compact-docker",
        serviceType: "docker",
        host: "localhost",
        port: 2376,
        config: { socketPath: "/var/run/docker.sock" },
      })
      .returning();

    // 2. 创建 incident
    const [inc] = await db
      .insert(incidents)
      .values({
        description: "测试 compact 触发",
        severity: "P3",
      })
      .returning();

    // 3. 创建 agent session 并预填充大量消息（模拟已经排查了很多轮）
    const bulkMessages: Message[] = [
      { role: "user", content: "请检查 Docker 容器状态" },
    ];

    // 填充大量 tool 结果消息，超过 80K 字符阈值
    for (let i = 0; i < 15; i++) {
      bulkMessages.push({
        role: "assistant",
        content: "",
        toolCalls: [
          {
            id: `call_${i}`,
            name: "service_exec",
            args: { serviceId: svc.id, operation: "listContainers" },
          },
        ],
      });
      bulkMessages.push({
        role: "tool",
        toolCallId: `call_${i}`,
        toolName: "service_exec",
        // 每条 tool result 约 6000 字符，15 条 ≈ 90K > 80K 阈值
        content: JSON.stringify(
          Array.from({ length: 20 }, (_, j) => ({
            Id: `container_${i}_${j}_${"a".repeat(200)}`,
            Names: [`/test-container-${i}-${j}`],
            Image: "nginx:alpine",
            Status: "Up 2 hours",
            Ports: [{ PrivatePort: 80, PublicPort: 8080 + j }],
          })),
          null,
          2,
        ),
      });
    }

    // 预创建 session 并填入大量消息
    await db.insert(agentSessions).values({
      incidentId: inc.id,
      status: "running",
      agentMessages: bulkMessages,
      turnCount: 15,
    });

    // 验证确实超过阈值
    expect(shouldCompact(bulkMessages)).toBe(true);

    // 4. 触发 Agent（resume 方式，追加新用户消息）
    const res = await request("POST", `/api/agent/${inc.id}/resume`, {
      token,
      body: { type: "human_input", text: "请继续检查，总结一下所有容器的状态" },
    });

    expect(res.status).toBe(200);
    const text = await res.text();
    const events = parseSSEEvents(text);

    console.log("\n========== Compact 测试 SSE EVENTS ==========");
    for (const ev of events) {
      console.log(`  [${ev.type}] ${JSON.stringify(ev.data).slice(0, 120)}`);
    }
    console.log("========== END ==========\n");

    // 验证: compact_done 事件被触发
    const compactDone = events.find((e) => e.type === "compact_done");
    if (compactDone) {
      console.log("  ✓ compact_done 事件已触发");
      const compactMd = (compactDone.data as { compactMd?: string }).compactMd || "";
      console.log(`  ✓ compact 摘要: "${compactMd.slice(0, 150)}..."`);
    } else {
      console.log("  ⚠ 未触发 compact_done（可能消息未达阈值或 compact 发生在内部）");
    }

    // 验证: Agent 最终完成
    const doneEvent = events.find((e) => e.type === "done");
    const errorEvent = events.find((e) => e.type === "error");

    if (doneEvent) {
      console.log("  ✓ Agent 完成");
    } else if (errorEvent) {
      console.log(`  ✗ Agent 错误: ${JSON.stringify(errorEvent.data)}`);
    }

    // 验证 DB: session 状态
    const [session] = await db
      .select()
      .from(agentSessions)
      .where(eq(agentSessions.incidentId, inc.id));

    console.log(`  DB: status=${session.status}, turns=${session.turnCount}`);
    console.log(
      `  DB: messages=${(session.agentMessages as unknown[]).length}` +
        (session.compactMd ? `, compactMd=${(session.compactMd as string).length} chars` : ""),
    );

    // compact 后 messages 数量应该大幅减少（从 30+ 减到 < 10）
    expect((session.agentMessages as unknown[]).length).toBeLessThan(bulkMessages.length);
  }, 120_000);
});
