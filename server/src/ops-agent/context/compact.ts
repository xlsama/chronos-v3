import { createOpenAI } from "@ai-sdk/openai";
import { generateText } from "ai";
import { env } from "../../env";
import { logger } from "../../lib/logger";
import type { AgentSession, Message } from "../types";
import { COMPACT_SYSTEM_PROMPT } from "./compact-prompts";

const log = logger.child({ component: "compact" });

const COMPACT_CHAR_THRESHOLD = 80_000;
const MAX_RECENT_CHARS = 8_000;

const openai = createOpenAI({
  baseURL: env.LLM_BASE_URL,
  apiKey: env.DASHSCOPE_API_KEY,
});

/**
 * 检查是否需要 compact。
 */
export function shouldCompact(messages: Message[]): boolean {
  const total = messages.reduce((sum, m) => {
    if (m.role === "tool") return sum + m.content.length;
    if (m.role === "assistant") {
      let len = m.content.length;
      if (m.toolCalls) len += JSON.stringify(m.toolCalls).length;
      return sum + len;
    }
    return sum + (m as { content: string }).content.length;
  }, 0);
  return total > COMPACT_CHAR_THRESHOLD;
}

/**
 * 检查 LLM 错误是否是 context length 超限。
 */
export function isContextLengthError(err: unknown): boolean {
  const msg = String(err).toLowerCase();
  return (
    msg.includes("context_length_exceeded") ||
    msg.includes("prompt is too long") ||
    msg.includes("maximum context length") ||
    msg.includes("input length") ||
    msg.includes("token limit")
  );
}

/**
 * 执行 compact：用 mini_model 生成结构化摘要。
 */
export async function compactMessages(session: AgentSession): Promise<string> {
  const sid = session.incidentId.slice(0, 8);
  log.info(`[COMPACT] START: incident=${sid}, messages=${session.agentMessages.length}`);

  const userPrompt = buildCompactInput(session);

  let content = "";
  try {
    const result = await generateText({
      model: openai(env.MINI_MODEL),
      system: COMPACT_SYSTEM_PROMPT,
      prompt: userPrompt,
    });
    content = result.text;
  } catch (err) {
    log.warn(`[COMPACT] LLM FAILED: ${(err as Error).message}, using fallback`);
    content = `（自动摘要失败）\n\n${userPrompt}`;
  }

  const summary = extractSummary(content);
  log.info(`[COMPACT] DONE: summary=${summary.length} chars`);
  return summary;
}

/**
 * Compact 后重建 agentMessages。
 * 替换为：摘要 + 计划（如果有）
 */
export function rebuildAfterCompact(session: AgentSession, compactMd: string): Message[] {
  const messages: Message[] = [
    { role: "user", content: `[历史排查摘要]\n\n${compactMd}` },
  ];

  if (session.planMd) {
    messages.push({
      role: "user",
      content: `[当前调查计划]\n\n${session.planMd}`,
    });
  }

  // 保留用户的原始提问（第一条 user 消息）
  const firstUserMsg = session.agentMessages.find((m) => m.role === "user");
  if (firstUserMsg && firstUserMsg.role === "user") {
    messages.push({
      role: "user",
      content: `[原始问题] ${firstUserMsg.content}`,
    });
  }

  messages.push({
    role: "user",
    content: "请基于以上摘要继续排查。",
  });

  return messages;
}

// ─── Internal helpers ──────────────────────────────────

function buildCompactInput(session: AgentSession): string {
  const parts: string[] = [];

  parts.push(`## 事件信息\n- 描述: ${getDescription(session)}`);

  if (session.planMd) {
    parts.push(`## 当前调查计划\n${session.planMd}`);
  }

  parts.push(`## 排查对话历史\n${formatRecentMessages(session.agentMessages, MAX_RECENT_CHARS)}`);

  return parts.join("\n\n");
}

function getDescription(session: AgentSession): string {
  const firstUser = session.agentMessages.find((m) => m.role === "user");
  if (firstUser && firstUser.role === "user") return firstUser.content;
  return "(未知)";
}

function formatRecentMessages(messages: Message[], maxChars: number): string {
  const parts: string[] = [];
  let total = 0;

  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    let text: string;

    switch (m.role) {
      case "user":
        text = `[user] ${m.content}`;
        break;
      case "assistant":
        text = `[assistant] ${m.content}`;
        if (m.toolCalls?.length) {
          text += `\n  tool_calls: ${m.toolCalls.map((tc) => tc.name).join(", ")}`;
        }
        break;
      case "tool":
        text = `[tool:${m.toolName}] ${truncate(m.content, 1500)}`;
        break;
      case "system":
        text = `[system] ${truncate(m.content, 500)}`;
        break;
      default:
        continue;
    }

    if (total + text.length > maxChars) break;
    parts.unshift(text);
    total += text.length;
  }

  return parts.join("\n\n");
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "...[截断]";
}

/** @internal 仅供测试使用 */
export function extractSummary(raw: string): string {
  // 移除 <analysis> 块
  const cleaned = raw.replace(/<analysis>[\s\S]*?<\/analysis>/i, "");

  // 提取 <summary> 内容
  const match = cleaned.match(/<summary>([\s\S]*?)<\/summary>/i);
  if (match) return match[1].trim();

  // 降级：返回清理后的全部内容
  return cleaned.trim() || raw.trim();
}
