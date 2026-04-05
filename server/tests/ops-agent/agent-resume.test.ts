import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { db } from "@/db/connection";
import { incidents, services, agentSessions } from "@/db/schema";
import { eq } from "drizzle-orm";
import { resumeAgent } from "@/ops-agent/resume";
import type { AgentEvent, Message } from "@/ops-agent/types";

// ─── fetch mock 辅助（复用 agent-loop.test.ts 的格式）─────

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, "fetch");
});

afterEach(() => {
  fetchSpy.mockRestore();
});

function buildLLMResponse(options: {
  text?: string;
  toolCalls?: Array<{ id: string; name: string; args: Record<string, unknown> }>;
}): Response {
  const output: Record<string, unknown>[] = [];

  if (options.text) {
    output.push({
      type: "message",
      id: "msg-1",
      role: "assistant",
      status: "completed",
      content: [{ type: "output_text", text: options.text, annotations: [] }],
    });
  }

  if (options.toolCalls?.length) {
    for (const tc of options.toolCalls) {
      output.push({
        type: "function_call",
        id: tc.id,
        call_id: tc.id,
        name: tc.name,
        arguments: JSON.stringify(tc.args),
        status: "completed",
      });
    }
  }

  if (output.length === 0) {
    output.push({
      type: "message",
      id: "msg-1",
      role: "assistant",
      status: "completed",
      content: [{ type: "output_text", text: "", annotations: [] }],
    });
  }

  return new Response(
    JSON.stringify({
      id: "resp-test",
      object: "response",
      model: "test-model",
      created_at: Date.now() / 1000,
      output,
      status: "completed",
      usage: { input_tokens: 100, output_tokens: 50, total_tokens: 150 },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

function mockFetchSequence(responses: Array<() => Response>) {
  let callIndex = 0;
  fetchSpy.mockImplementation(async () => {
    if (callIndex < responses.length) {
      return responses[callIndex++]();
    }
    return new Response(
      JSON.stringify({ error: { message: "Unauthorized", type: "auth_error" } }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    );
  });
}

async function collectEvents(gen: AsyncGenerator<AgentEvent>): Promise<AgentEvent[]> {
  const events: AgentEvent[] = [];
  for await (const event of gen) {
    events.push(event);
  }
  return events;
}

// ─── 辅助：创建 interrupted session ─────────────────────────

async function createInterruptedSession(overrides: {
  agentMessages?: Message[];
  pendingToolCall?: Record<string, unknown> | null;
  pendingApprovalId?: string | null;
  summary?: string | null;
} = {}) {
  const [inc] = await db
    .insert(incidents)
    .values({ description: "resume 测试事件", severity: "P3" })
    .returning();

  const values: Record<string, unknown> = {
    incidentId: inc.id,
    status: "interrupted",
    agentMessages: overrides.agentMessages || [
      { role: "user", content: "检查容器" },
      { role: "assistant", content: "我来检查", toolCalls: [{ id: "tc1", name: "ask_user_question", args: { question: "请确认" } }] },
      { role: "tool", toolCallId: "tc1", toolName: "ask_user_question", content: "已向用户提问" },
    ],
    turnCount: 3,
    interruptedAt: new Date(),
  };

  if (overrides.pendingToolCall !== undefined) values.pendingToolCall = overrides.pendingToolCall;
  if (overrides.pendingApprovalId !== undefined) values.pendingApprovalId = overrides.pendingApprovalId;
  if (overrides.summary !== undefined) values.summary = overrides.summary;

  await db.insert(agentSessions).values(values as typeof agentSessions.$inferInsert);

  return inc.id;
}

async function getSession(incidentId: string) {
  const [session] = await db
    .select()
    .from(agentSessions)
    .where(eq(agentSessions.incidentId, incidentId))
    .limit(1);
  return session;
}

// ─── C1: 无 session → 抛错 ───────────────────────────────

describe("Resume — no session", () => {
  it("不存在的 incidentId 抛出错误", async () => {
    // 创建 incident 但不创建 session
    const [inc] = await db
      .insert(incidents)
      .values({ description: "no session test", severity: "P3" })
      .returning();
    const gen = resumeAgent(inc.id, { type: "human_input", text: "hello" });
    await expect(collectEvents(gen)).rejects.toThrow("No agent session found");
  });
});

// ─── C2: approval 无 pendingToolCall → 抛错 ──────────────

describe("Resume — approval without pending tool", () => {
  it("没有 pendingToolCall 时抛出错误", async () => {
    const incidentId = await createInterruptedSession({ pendingToolCall: null });
    const gen = resumeAgent(incidentId, { type: "approval", decision: "approved" });
    await expect(collectEvents(gen)).rejects.toThrow("No pending tool call");
  });
});

// ─── C3: approval approved → 执行工具 → 继续 ─────────────

describe("Resume — approval approved", () => {
  it("批准后执行待审批工具并继续主循环", async () => {
    const [svc] = await db
      .insert(services)
      .values({
        name: `resume-docker-${Date.now()}`,
        serviceType: "docker",
        host: "localhost",
        port: 2376,
        config: { socketPath: "/var/run/docker.sock" },
      })
      .returning();

    const incidentId = await createInterruptedSession({
      pendingToolCall: {
        id: "tc_pending",
        name: "service_exec",
        args: { serviceId: svc.id, operation: "listContainers", parameters: {} },
      },
      pendingApprovalId: crypto.randomUUID(),
    });

    mockFetchSequence([
      // runAgent 继续后 LLM 直接完成
      () => buildLLMResponse({ text: "容器列表已获取，排查完成" }),
    ]);

    const events = await collectEvents(
      resumeAgent(incidentId, { type: "approval", decision: "approved" }),
    );
    const types = events.map((e) => e.type);

    expect(types).toContain("resumed");
    expect(types).toContain("tool_start");
    expect(types).toContain("tool_result");
    expect(types).toContain("done");

    const session = await getSession(incidentId);
    expect(session.status).toBe("completed");
    expect(session.pendingToolCall).toBeNull();
    expect(session.pendingApprovalId).toBeNull();
  });
});

// ─── C4: approval rejected → 跳过 → 继续 ─────────────────

describe("Resume — approval rejected", () => {
  it("拒绝后跳过工具并继续排查", async () => {
    const incidentId = await createInterruptedSession({
      pendingToolCall: {
        id: "tc_pending",
        name: "service_exec",
        args: { serviceId: "svc-1", operation: "deleteContainer", parameters: {} },
      },
      pendingApprovalId: crypto.randomUUID(),
    });

    mockFetchSequence([
      () => buildLLMResponse({ text: "好的，不删除容器了" }),
    ]);

    const events = await collectEvents(
      resumeAgent(incidentId, { type: "approval", decision: "rejected", feedback: "太危险了" }),
    );
    const types = events.map((e) => e.type);

    expect(types).toContain("resumed");
    expect(types).toContain("approval_result");
    expect(types).toContain("done");
    // 不应有 tool_start（工具被跳过）
    expect(types).not.toContain("tool_start");

    const session = await getSession(incidentId);
    expect(session.status).toBe("completed");

    // 验证拒绝消息被添加到 agentMessages
    const messages = session.agentMessages as Message[];
    const rejectMsg = messages.find(
      (m) => m.role === "tool" && m.content.includes("用户拒绝操作"),
    );
    expect(rejectMsg).toBeDefined();
  });
});

// ─── C5: confirm confirmed=true → 直接完成 ────────────────

describe("Resume — confirm done", () => {
  it("确认已解决时直接完成（不进入主循环）", async () => {
    const incidentId = await createInterruptedSession({
      summary: "问题已修复：重启容器后恢复",
    });

    // 不需要 mock，因为 confirm=true 不会调用 runAgent
    const events = await collectEvents(
      resumeAgent(incidentId, { type: "confirm", confirmed: true }),
    );
    const types = events.map((e) => e.type);

    expect(types).toContain("resumed");
    expect(types).toContain("done");
    // 不应有 session_started（不进入 runAgent）
    expect(types).not.toContain("session_started");

    const done = events.find((e) => e.type === "done")!;
    expect((done.data as { finalSummary: string }).finalSummary).toContain("问题已修复");

    const session = await getSession(incidentId);
    expect(session.status).toBe("completed");
  });
});

// ─── C6: confirm confirmed=false → 继续排查 ──────────────

describe("Resume — confirm continue", () => {
  it("确认未解决时继续排查", async () => {
    const incidentId = await createInterruptedSession();

    mockFetchSequence([
      () => buildLLMResponse({ text: "继续排查中..." }),
    ]);

    const events = await collectEvents(
      resumeAgent(incidentId, { type: "confirm", confirmed: false, text: "还是有问题" }),
    );
    const types = events.map((e) => e.type);

    expect(types).toContain("resumed");
    expect(types).toContain("done");

    // 验证添加了 [问题未解决] 消息
    const session = await getSession(incidentId);
    const messages = session.agentMessages as Message[];
    const continueMsg = messages.find(
      (m) => m.role === "user" && m.content.includes("[问题未解决]"),
    );
    expect(continueMsg).toBeDefined();
  });
});

// ─── C7: human_input → 添加消息 → 继续 ───────────────────

describe("Resume — human_input", () => {
  it("用户输入后添加消息并继续排查", async () => {
    const incidentId = await createInterruptedSession();

    mockFetchSequence([
      () => buildLLMResponse({ text: "收到，服务ID是abc123" }),
    ]);

    const events = await collectEvents(
      resumeAgent(incidentId, { type: "human_input", text: "服务ID是abc123" }),
    );
    const types = events.map((e) => e.type);

    expect(types).toContain("resumed");
    expect(types).toContain("done");

    const session = await getSession(incidentId);
    const messages = session.agentMessages as Message[];
    const userMsg = messages.find(
      (m) => m.role === "user" && m.content === "服务ID是abc123",
    );
    expect(userMsg).toBeDefined();
    expect(session.status).toBe("completed");
  });
});
