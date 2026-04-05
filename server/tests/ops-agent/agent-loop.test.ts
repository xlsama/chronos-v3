import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { db } from "@/db/connection";
import { incidents, services, agentSessions, approvalRequests } from "@/db/schema";
import { eq } from "drizzle-orm";
import { runAgent } from "@/ops-agent/agent-loop";
import type { AgentEvent } from "@/ops-agent/types";

// ─── fetch mock 辅助（OpenAI Responses API 格式）────────────

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, "fetch");
});

afterEach(() => {
  fetchSpy.mockRestore();
});

/**
 * 构造 OpenAI Responses API 格式的 mock 响应
 * AI SDK v6 + @ai-sdk/openai v3 使用 /responses 端点
 */
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

function buildErrorResponse(message: string, status = 400): Response {
  return new Response(
    JSON.stringify({ error: { message, type: "invalid_request_error" } }),
    { status, headers: { "Content-Type": "application/json" } },
  );
}

/**
 * 使用 mockImplementation + 调用计数器，确保每次返回新的 Response 对象
 */
function mockFetchSequence(responses: Array<() => Response>) {
  let callIndex = 0;
  fetchSpy.mockImplementation(async () => {
    if (callIndex < responses.length) {
      return responses[callIndex++]();
    }
    return buildErrorResponse("no more mocks: Unauthorized", 401);
  });
}

async function collectEvents(gen: AsyncGenerator<AgentEvent>): Promise<AgentEvent[]> {
  const events: AgentEvent[] = [];
  for await (const event of gen) {
    events.push(event);
  }
  return events;
}

// ─── 测试辅助 ─────────────────────────────────────────────

async function createIncident(description = "测试事件"): Promise<string> {
  const [inc] = await db
    .insert(incidents)
    .values({ description, severity: "P3" })
    .returning();
  return inc.id;
}

async function getSession(iid: string): Promise<typeof agentSessions.$inferSelect> {
  const [session] = await db
    .select()
    .from(agentSessions)
    .where(eq(agentSessions.incidentId, iid))
    .limit(1);
  return session;
}

// ─── B1: completed — LLM 无 toolCall 直接完成 ────────────

describe("Agent Loop — completed", () => {
  it("LLM 返回纯文本时正常完成", async () => {
    const incidentId = await createIncident();
    mockFetchSequence([
      () => buildLLMResponse({ text: "检查完毕，一切正常" }),
    ]);

    const events = await collectEvents(runAgent(incidentId, "检查容器"));
    const types = events.map((e) => e.type);

    expect(types).toContain("session_started");
    expect(types).toContain("thinking");
    expect(types).toContain("done");

    const done = events.find((e) => e.type === "done")!;
    expect((done.data as { finalSummary: string }).finalSummary).toContain("检查完毕");

    const session = await getSession(incidentId);
    expect(session.status).toBe("completed");
    expect(session.summary).toContain("检查完毕");
    expect(session.turnCount).toBe(1);
  });
});

// ─── B2: max_turns — 达到最大轮次终止 ─────────────────────

describe("Agent Loop — max_turns", () => {
  it("达到 maxTurns 时终止并标记 failed", async () => {
    const incidentId = await createIncident();

    // 预创建 session，turnCount 已经是 maxTurns
    await db.insert(agentSessions).values({
      incidentId,
      status: "running",
      agentMessages: [{ role: "user", content: "检查容器" }],
      turnCount: 40,
      maxTurns: 40,
    });

    const events = await collectEvents(runAgent(incidentId));
    const types = events.map((e) => e.type);

    expect(types).toContain("session_started");
    expect(types).toContain("error");

    const errorEvent = events.find((e) => e.type === "error")!;
    expect((errorEvent.data as { message: string }).message).toContain("最大循环次数");

    const session = await getSession(incidentId);
    expect(session.status).toBe("failed");
  });
});

// ─── B3: ask_user_question — 中断等待用户 ─────────────────

describe("Agent Loop — ask_user_question", () => {
  it("调用 ask_user_question 时中断并保存状态", async () => {
    const incidentId = await createIncident();
    mockFetchSequence([
      () => buildLLMResponse({
        text: "我需要更多信息",
        toolCalls: [
          { id: "tc_ask", name: "ask_user_question", args: { question: "请提供日志路径" } },
        ],
      }),
    ]);

    const events = await collectEvents(runAgent(incidentId, "nginx 502"));
    const types = events.map((e) => e.type);

    expect(types).toContain("session_started");
    expect(types).toContain("thinking");
    expect(types).toContain("ask_user_question");
    expect(types).not.toContain("done");

    const askEvent = events.find((e) => e.type === "ask_user_question")!;
    expect((askEvent.data as { question: string }).question).toContain("日志路径");

    const session = await getSession(incidentId);
    expect(session.status).toBe("interrupted");
    expect(session.interruptedAt).not.toBeNull();
  });
});

// ─── B4: 危险操作 → approval_required 中断 ────────────────

describe("Agent Loop — approval_required", () => {
  it("危险操作触发审批中断", async () => {
    const incidentId = await createIncident();

    const [svc] = await db
      .insert(services)
      .values({
        name: `test-docker-${Date.now()}`,
        serviceType: "docker",
        host: "localhost",
        port: 2376,
        config: { socketPath: "/var/run/docker.sock" },
      })
      .returning();

    mockFetchSequence([
      () => buildLLMResponse({
        text: "需要删除容器",
        toolCalls: [
          {
            id: "tc_del",
            name: "service_exec",
            args: {
              serviceId: svc.id,
              operation: "deleteContainer",
              parameters: { containerId: "abc123" },
            },
          },
        ],
      }),
    ]);

    const events = await collectEvents(runAgent(incidentId, "清理容器"));
    const types = events.map((e) => e.type);

    expect(types).toContain("approval_required");
    expect(types).not.toContain("done");

    const approvalEvent = events.find((e) => e.type === "approval_required")!;
    const data = approvalEvent.data as {
      approvalId: string;
      toolName: string;
      riskLevel: string;
    };
    expect(data.toolName).toBe("service_exec");
    expect(data.riskLevel).toBe("HIGH");
    expect(data.approvalId).toBeTruthy();

    const session = await getSession(incidentId);
    expect(session.status).toBe("interrupted");
    expect(session.pendingToolCall).not.toBeNull();
    expect(session.pendingApprovalId).toBeTruthy();

    const [approval] = await db
      .select()
      .from(approvalRequests)
      .where(eq(approvalRequests.incidentId, incidentId))
      .limit(1);
    expect(approval).toBeDefined();
    expect(approval.toolName).toBe("service_exec");
    expect(approval.riskLevel).toBe("HIGH");
  });
});

// ─── B5: 工具执行异常 → toolError + 继续 ──────────────────

describe("Agent Loop — tool execution error", () => {
  it("工具执行失败时记录错误并继续下一轮", async () => {
    const incidentId = await createIncident();

    mockFetchSequence([
      // 轮 1: 调用不存在的 serviceId → execute 抛错
      () => buildLLMResponse({
        toolCalls: [
          {
            id: "tc_err",
            name: "service_exec",
            args: {
              serviceId: "nonexistent-id",
              operation: "listContainers",
              parameters: {},
            },
          },
        ],
      }),
      // 轮 2: LLM 看到错误后直接完成
      () => buildLLMResponse({ text: "无法连接服务" }),
    ]);

    const events = await collectEvents(runAgent(incidentId, "检查容器"));
    const types = events.map((e) => e.type);

    expect(types).toContain("tool_error");
    expect(types).toContain("done");

    const toolError = events.find((e) => e.type === "tool_error")!;
    expect((toolError.data as { error: string }).error).toContain("执行失败");

    const session = await getSession(incidentId);
    expect(session.status).toBe("completed");
  });
});

// ─── B6: 未知工具名 → toolError + 继续 ────────────────────

describe("Agent Loop — unknown tool", () => {
  it("LLM 返回不存在的工具名时记录错误并继续", async () => {
    const incidentId = await createIncident();

    mockFetchSequence([
      () => buildLLMResponse({
        toolCalls: [
          { id: "tc_unk", name: "nonexistent_tool", args: {} },
        ],
      }),
      () => buildLLMResponse({ text: "好的，我换个方式" }),
    ]);

    const events = await collectEvents(runAgent(incidentId, "检查"));
    const types = events.map((e) => e.type);

    expect(types).toContain("tool_error");
    expect(types).toContain("done");

    const toolError = events.find((e) => e.type === "tool_error")!;
    expect((toolError.data as { error: string }).error).toContain("未知工具");
  });
});

// ─── B7: LLM 非上下文错误 → failed ───────────────────────

describe("Agent Loop — LLM error", () => {
  it("LLM 返回非上下文错误时标记 failed", async () => {
    const incidentId = await createIncident();

    mockFetchSequence([
      () => buildErrorResponse("internal server error", 500),
    ]);

    const events = await collectEvents(runAgent(incidentId, "检查"));
    const types = events.map((e) => e.type);

    expect(types).toContain("error");

    const errorEvent = events.find((e) => e.type === "error")!;
    expect((errorEvent.data as { fatal: boolean }).fatal).toBe(true);

    const session = await getSession(incidentId);
    expect(session.status).toBe("failed");
  });
});

// ─── B8: 被动 compact 成功 → 重试 ────────────────────────

describe("Agent Loop — reactive compact success", () => {
  it("context_length_exceeded 触发被动 compact 后重试成功", async () => {
    const incidentId = await createIncident();

    mockFetchSequence([
      // 主 LLM: context length 错误
      () => buildErrorResponse("This model's maximum context length is exceeded", 400),
      // compact LLM (mini model): 成功返回摘要
      () => buildLLMResponse({ text: "<summary>历史排查摘要：检查了容器状态</summary>" }),
      // 主 LLM 重试: 成功完成
      () => buildLLMResponse({ text: "基于摘要完成分析" }),
    ]);

    const events = await collectEvents(runAgent(incidentId, "检查容器"));
    const types = events.map((e) => e.type);

    expect(types).toContain("compact_done");
    expect(types).toContain("done");

    const session = await getSession(incidentId);
    expect(session.status).toBe("completed");
    expect(session.compactMd).toBeTruthy();
  });
});

// ─── B9: 被动 compact 也失败 → context_too_long ──────────

describe("Agent Loop — reactive compact failure", () => {
  it("compact 也失败时标记 failed", async () => {
    const incidentId = await createIncident();

    mockFetchSequence([
      // 主 LLM: context length 错误
      () => buildErrorResponse("maximum context length exceeded", 400),
      // compact LLM: 也失败（compact.ts 会 catch 并使用 fallback）
      () => buildErrorResponse("server overloaded", 500),
      // 主 LLM 重试后仍然失败（compact 的 fallback 摘要可能仍然太长）
      // compact fallback 不会 throw，所以 agent 会重试主 LLM
      // 但 compactFailures 已经 +1，重试的 LLM 仍然可能失败
      () => buildErrorResponse("still too long context length exceeded", 400),
      // 第二次 compact
      () => buildErrorResponse("server still down", 500),
      // 第二次重试
      () => buildErrorResponse("context length exceeded again", 400),
      // 第三次 compact — 但 compactFailures >= MAX_COMPACT_FAILURES，不再尝试
    ]);

    const events = await collectEvents(runAgent(incidentId, "检查"));
    const types = events.map((e) => e.type);

    expect(types).toContain("error");

    const session = await getSession(incidentId);
    expect(session.status).toBe("failed");
  });
});

// ─── B10: update_plan 特殊处理 ────────────────────────────

describe("Agent Loop — update_plan", () => {
  it("调用 update_plan 时保存 planMd 并触发 plan_updated 事件", async () => {
    const incidentId = await createIncident();
    const planMd = "## 调查计划\n1. 检查容器状态\n2. 查看日志";

    mockFetchSequence([
      () => buildLLMResponse({
        toolCalls: [
          {
            id: "tc_plan",
            name: "update_plan",
            args: { planMd, intent: "incident" },
          },
        ],
      }),
      () => buildLLMResponse({ text: "计划已制定，开始排查" }),
    ]);

    const events = await collectEvents(runAgent(incidentId, "nginx 异常"));
    const types = events.map((e) => e.type);

    expect(types).toContain("plan_updated");
    expect(types).toContain("done");

    const planEvent = events.find((e) => e.type === "plan_updated")!;
    const data = planEvent.data as { planMd: string; intent?: string };
    expect(data.planMd).toBe(planMd);
    expect(data.intent).toBe("incident");

    const session = await getSession(incidentId);
    expect(session.planMd).toBe(planMd);
  });
});
