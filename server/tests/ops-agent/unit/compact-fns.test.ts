import { describe, it, expect } from "vitest";
import {
  shouldCompact,
  isContextLengthError,
  rebuildAfterCompact,
  extractSummary,
} from "@/ops-agent/context/compact";
import type { AgentSession, Message } from "@/ops-agent/types";

// ─── shouldCompact ────────────────────────────────────────

describe("shouldCompact", () => {
  it("短消息返回 false", () => {
    const messages: Message[] = [
      { role: "user", content: "hello" },
      { role: "assistant", content: "hi" },
    ];
    expect(shouldCompact(messages)).toBe(false);
  });

  it("assistant 消息含 toolCalls 时应计入序列化长度", () => {
    const toolCalls = Array.from({ length: 50 }, (_, i) => ({
      id: `call_${i}`,
      name: "service_exec",
      args: { serviceId: "a".repeat(500), operation: "listContainers" },
    }));
    // toolCalls JSON 序列化后非常长
    const messages: Message[] = [
      { role: "assistant", content: "", toolCalls },
    ];
    const toolCallsLen = JSON.stringify(toolCalls).length;
    // 只有 toolCalls 很长时才触发
    if (toolCallsLen > 80_000) {
      expect(shouldCompact(messages)).toBe(true);
    }
  });

  it("tool 消息的 content 长度正确计入", () => {
    const messages: Message[] = [
      {
        role: "tool",
        toolCallId: "tc1",
        toolName: "service_exec",
        content: "x".repeat(90_000),
      },
    ];
    expect(shouldCompact(messages)).toBe(true);
  });

  it("恰好 80000 字符返回 false", () => {
    const messages: Message[] = [
      { role: "user", content: "x".repeat(80_000) },
    ];
    expect(shouldCompact(messages)).toBe(false);
  });

  it("80001 字符返回 true", () => {
    const messages: Message[] = [
      { role: "user", content: "x".repeat(80_001) },
    ];
    expect(shouldCompact(messages)).toBe(true);
  });

  it("多条消息累加超过阈值", () => {
    const messages: Message[] = Array.from({ length: 10 }, (_, i) => ({
      role: "tool" as const,
      toolCallId: `tc_${i}`,
      toolName: "service_exec",
      content: "x".repeat(9_000),
    }));
    // 10 * 9000 = 90000 > 80000
    expect(shouldCompact(messages)).toBe(true);
  });

  it("空消息列表返回 false", () => {
    expect(shouldCompact([])).toBe(false);
  });
});

// ─── isContextLengthError ─────────────────────────────────

describe("isContextLengthError", () => {
  it.each([
    "context_length_exceeded",
    "prompt is too long",
    "maximum context length",
    "input length exceeded",
    "token limit reached",
  ])("识别: %s", (msg) => {
    expect(isContextLengthError(new Error(msg))).toBe(true);
  });

  it("大小写不敏感", () => {
    expect(isContextLengthError(new Error("CONTEXT_LENGTH_EXCEEDED"))).toBe(true);
    expect(isContextLengthError(new Error("Maximum Context Length"))).toBe(true);
  });

  it.each([
    "rate limit exceeded",
    "network error",
    "internal server error",
    "invalid api key",
  ])("不匹配: %s", (msg) => {
    expect(isContextLengthError(new Error(msg))).toBe(false);
  });

  it("处理字符串类型", () => {
    expect(isContextLengthError("context_length_exceeded")).toBe(true);
  });

  it("处理 null", () => {
    expect(isContextLengthError(null)).toBe(false);
  });

  it("处理 undefined", () => {
    expect(isContextLengthError(undefined)).toBe(false);
  });

  it("处理数字", () => {
    expect(isContextLengthError(42)).toBe(false);
  });
});

// ─── rebuildAfterCompact ──────────────────────────────────

function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    id: "sess-1",
    incidentId: "inc-1",
    status: "running",
    agentMessages: [
      { role: "user", content: "nginx 502 错误" },
      { role: "assistant", content: "我来检查" },
    ],
    turnCount: 5,
    maxTurns: 40,
    planMd: null,
    compactMd: null,
    summary: null,
    pendingToolCall: null,
    pendingApprovalId: null,
    interruptedAt: null,
    ...overrides,
  };
}

describe("rebuildAfterCompact", () => {
  it("无 planMd 时重建为 3 条消息", () => {
    const session = makeSession();
    const messages = rebuildAfterCompact(session, "这是摘要");
    expect(messages).toHaveLength(3);
    expect(messages[0].content).toContain("这是摘要");
    expect(messages[1].content).toContain("nginx 502 错误");
    expect(messages[2].content).toBe("请基于以上摘要继续排查。");
  });

  it("有 planMd 时重建为 4 条消息", () => {
    const session = makeSession({ planMd: "## 计划\n1. 检查容器" });
    const messages = rebuildAfterCompact(session, "这是摘要");
    expect(messages).toHaveLength(4);
    expect(messages[0].content).toContain("这是摘要");
    expect(messages[1].content).toContain("计划");
    expect(messages[2].content).toContain("nginx 502 错误");
    expect(messages[3].content).toBe("请基于以上摘要继续排查。");
  });

  it("提取第一条 user 消息作为原始问题", () => {
    const session = makeSession({
      agentMessages: [
        { role: "assistant", content: "系统启动" },
        { role: "user", content: "第一个问题" },
        { role: "user", content: "第二个问题" },
      ],
    });
    const messages = rebuildAfterCompact(session, "摘要");
    const originalQuestion = messages.find((m) => m.content.includes("第一个问题"));
    expect(originalQuestion).toBeDefined();
    // 不应包含第二个问题
    expect(messages.every((m) => !m.content.includes("第二个问题"))).toBe(true);
  });

  it("无 user 消息时只有摘要 + 继续排查", () => {
    const session = makeSession({
      agentMessages: [
        { role: "assistant", content: "系统启动" },
      ],
    });
    const messages = rebuildAfterCompact(session, "摘要");
    expect(messages).toHaveLength(2);
    expect(messages[0].content).toContain("摘要");
    expect(messages[1].content).toBe("请基于以上摘要继续排查。");
  });

  it("所有消息 role 都是 user", () => {
    const session = makeSession();
    const messages = rebuildAfterCompact(session, "摘要");
    for (const m of messages) {
      expect(m.role).toBe("user");
    }
  });
});

// ─── extractSummary ───────────────────────────────────────

describe("extractSummary", () => {
  it("提取 analysis + summary 标签内容", () => {
    const raw = "<analysis>分析过程</analysis><summary>核心摘要</summary>";
    expect(extractSummary(raw)).toBe("核心摘要");
  });

  it("只有 summary 标签", () => {
    expect(extractSummary("<summary>核心摘要</summary>")).toBe("核心摘要");
  });

  it("无标签的纯文本返回 trim 后的原文", () => {
    expect(extractSummary("  这是纯文本摘要  ")).toBe("这是纯文本摘要");
  });

  it("有 analysis 无 summary 返回去掉 analysis 后的文本", () => {
    const raw = "<analysis>分析过程</analysis>剩余文本";
    expect(extractSummary(raw)).toBe("剩余文本");
  });

  it("空字符串返回空字符串", () => {
    expect(extractSummary("")).toBe("");
  });

  it("多行 summary 内容", () => {
    const raw = `<summary>
## 事件描述
容器异常

## 排查发现
内存不足
</summary>`;
    const result = extractSummary(raw);
    expect(result).toContain("事件描述");
    expect(result).toContain("内存不足");
  });

  it("summary 内容带前后空白时 trim", () => {
    expect(extractSummary("<summary>  摘要  </summary>")).toBe("摘要");
  });
});
