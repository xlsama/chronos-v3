import { createOpenAI } from "@ai-sdk/openai";
import { generateText, tool as aiTool } from "ai";
import type { ToolSet } from "ai";
import { z } from "zod";
import { env } from "../env";
import { logger } from "../lib/logger";
import type { AgentEvent, Message, TerminalReason, ToolCall, ToolDefinition } from "./types";
import { buildToolRegistry } from "./tools/registry";
import { getSystemPrompt } from "./context/system-prompt";
import { truncateOutput } from "./context/truncation";
import {
  shouldCompact,
  isContextLengthError,
  compactMessages,
  rebuildAfterCompact,
} from "./context/compact";
import { AgentEventPublisher } from "./events/publisher";
import { saveSession, loadOrCreateSession, createApproval } from "./session";

const log = logger.child({ component: "agent" });
const MAX_COMPACT_FAILURES = 3;

const openai = createOpenAI({
  baseURL: env.LLM_BASE_URL,
  apiKey: env.DASHSCOPE_API_KEY,
});

function toolDefinitionsToAISDK(tools: ToolDefinition[]): ToolSet {
  const result: ToolSet = {};
  for (const t of tools) {
    result[t.name] = aiTool({
      description: t.description,
      inputSchema: t.parameters as z.ZodType,
    });
  }
  return result;
}

function agentMessagesToPrompt(msgs: Message[]) {
  return msgs.map((m) => {
    switch (m.role) {
      case "system":
        return { role: "system" as const, content: m.content };
      case "user":
        return { role: "user" as const, content: m.content };
      case "assistant":
        if (m.toolCalls?.length) {
          return {
            role: "assistant" as const,
            content: [
              ...(m.content ? [{ type: "text" as const, text: m.content }] : []),
              ...m.toolCalls.map((tc) => ({
                type: "tool-call" as const,
                toolCallId: tc.id,
                toolName: tc.name,
                input: tc.args,
              })),
            ],
          };
        }
        return { role: "assistant" as const, content: m.content };
      case "tool":
        return {
          role: "tool" as const,
          content: [
            {
              type: "tool-result" as const,
              toolCallId: m.toolCallId,
              toolName: m.toolName,
              output: { type: "text" as const, value: m.content },
            },
          ],
        };
    }
  });
}

export async function* runAgent(
  incidentId: string,
  initialPrompt?: string,
): AsyncGenerator<AgentEvent> {
  const sid = incidentId.slice(0, 8);
  log.info(`[AGENT] ========== SESSION START ========== incident=${sid}`);

  const session = await loadOrCreateSession(incidentId);
  const pub = new AgentEventPublisher(incidentId);

  if (initialPrompt) {
    session.agentMessages.push({ role: "user", content: initialPrompt });
    log.info(`[AGENT] INITIAL PROMPT: "${initialPrompt.slice(0, 100)}..."`);
  }

  const tools = buildToolRegistry();
  const aiTools = toolDefinitionsToAISDK(tools);

  let compactFailures = 0;
  let terminalReason: TerminalReason = "completed";

  yield pub.sessionStarted();

  while (true) {
    // 1. 防死循环
    session.turnCount++;
    log.info(`[AGENT] ========== TURN ${session.turnCount} START ==========`);

    if (session.turnCount > session.maxTurns) {
      log.error(`[AGENT] MAX TURNS REACHED: ${session.maxTurns}, aborting`);
      yield pub.error("达到最大循环次数，任务终止", true);
      session.status = "failed";
      terminalReason = "max_turns";
      break;
    }

    // 2. 主动 compact 检查
    if (shouldCompact(session.agentMessages)) {
      log.info(`[AGENT] PROACTIVE COMPACT: messages too long, compacting...`);
      try {
        const compactMd = await compactMessages(session);
        session.compactMd = compactMd;
        session.agentMessages = rebuildAfterCompact(session, compactMd);
        compactFailures = 0;
        yield pub.compactDone(compactMd);
        log.info(`[AGENT] COMPACT DONE: rebuilt ${session.agentMessages.length} messages`);
      } catch (err) {
        compactFailures++;
        log.error(`[AGENT] COMPACT FAILED (${compactFailures}/${MAX_COMPACT_FAILURES}): ${(err as Error).message}`);
        if (compactFailures >= MAX_COMPACT_FAILURES) {
          yield pub.error("上下文压缩连续失败，任务终止", true);
          session.status = "failed";
          terminalReason = "context_too_long";
          break;
        }
      }
    }

    // 3. 调用 LLM
    const systemPrompt = await getSystemPrompt(session);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const promptMessages = agentMessagesToPrompt(session.agentMessages) as any;

    log.info(
      `[AGENT] CALLING LLM: model=${env.MAIN_MODEL}, messages=${session.agentMessages.length}`,
    );
    log.debug(`[AGENT] SYSTEM PROMPT: "${systemPrompt.slice(0, 200)}..."`);

    let result;
    try {
      result = await generateText({
        model: openai(env.MAIN_MODEL),
        system: systemPrompt,
        messages: promptMessages,
        tools: aiTools,
      });
    } catch (err) {
      // 被动 compact：context_length_exceeded → compact → 重试
      if (isContextLengthError(err) && compactFailures < MAX_COMPACT_FAILURES) {
        compactFailures++;
        log.warn(
          `[AGENT] CONTEXT LENGTH EXCEEDED, attempting compact (${compactFailures}/${MAX_COMPACT_FAILURES})`,
        );
        try {
          const compactMd = await compactMessages(session);
          session.compactMd = compactMd;
          session.agentMessages = rebuildAfterCompact(session, compactMd);
          yield pub.compactDone(compactMd);
          log.info(`[AGENT] REACTIVE COMPACT DONE: rebuilt ${session.agentMessages.length} messages`);
          session.turnCount--; // 这轮不算，重试
          continue;
        } catch (compactErr) {
          log.error(`[AGENT] REACTIVE COMPACT FAILED: ${(compactErr as Error).message}`);
        }
      }

      log.error(`[AGENT] LLM ERROR: ${(err as Error).message}`);
      yield pub.error(`LLM 调用失败: ${(err as Error).message}`, true);
      session.status = "failed";
      terminalReason = isContextLengthError(err) ? "context_too_long" : "failed";
      break;
    }

    // 4. 收集 assistant 回复
    const assistantText = result.text || "";
    const toolCalls: ToolCall[] = result.toolCalls.map((tc) => {
      const input =
        "input" in tc ? tc.input : "args" in tc ? (tc as Record<string, unknown>).args : {};
      return {
        id: tc.toolCallId,
        name: tc.toolName,
        args: (typeof input === "object" && input !== null ? input : {}) as Record<
          string,
          unknown
        >,
      };
    });

    log.info(
      `[AGENT] LLM RESPONSE: text=${assistantText.length} chars, toolCalls=${toolCalls.length}${toolCalls.length > 0 ? ` [${toolCalls.map((tc) => tc.name).join(", ")}]` : ""}`,
    );
    if (assistantText) {
      log.debug(`[AGENT] LLM TEXT: "${assistantText.slice(0, 300)}..."`);
    }

    const assistantMessage: Message = {
      role: "assistant",
      content: assistantText,
      toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
    };
    session.agentMessages.push(assistantMessage);

    if (assistantText) {
      yield pub.thinking(assistantText);
    }

    // 5. 没有 tool call → 完成
    if (toolCalls.length === 0) {
      session.status = "completed";
      session.summary = assistantText;
      terminalReason = "completed";
      log.info(
        `[AGENT] ========== COMPLETED ========== turns=${session.turnCount}, summary=${assistantText.length} chars`,
      );
      yield pub.done(assistantText, session.turnCount);
      break;
    }

    // 6. 执行工具
    const events: AgentEvent[] = [];

    for (const tc of toolCalls) {
      log.info(
        `[AGENT] TOOL CALL: name=${tc.name}, args=${JSON.stringify(tc.args).slice(0, 200)}`,
      );

      const toolDef = tools.find((t) => t.name === tc.name);
      if (!toolDef) {
        const errMsg = `未知工具: ${tc.name}`;
        log.warn(`[AGENT] TOOL NOT FOUND: ${tc.name}`);
        session.agentMessages.push({
          role: "tool",
          toolCallId: tc.id,
          toolName: tc.name,
          content: errMsg,
        });
        const ev = pub.toolError(tc.name, errMsg);
        yield ev;
        events.push(ev);
        continue;
      }

      // ask_user_question: 中断等用户回复
      if (tc.name === "ask_user_question") {
        const question = (tc.args as { question: string }).question;
        log.info(`[AGENT] INTERRUPTED: ask_user_question, question="${question.slice(0, 100)}"`);
        session.agentMessages.push({
          role: "tool",
          toolCallId: tc.id,
          toolName: tc.name,
          content: `已向用户提问: ${question}`,
        });
        session.status = "interrupted";
        session.interruptedAt = new Date();
        const ev = pub.askUserQuestion(question);
        yield ev;
        events.push(ev);
        await saveSession(session, events);
        log.info(
          `[AGENT] SESSION SAVED: turn=${session.turnCount}, status=interrupted, messages=${session.agentMessages.length}`,
        );
        return; // terminalReason = "interrupted"
      }

      // 权限检查
      if (toolDef.needsPermissionCheck && toolDef.checkPermission) {
        const perm = await toolDef.checkPermission(tc.args);
        log.info(
          `[AGENT] PERMISSION CHECK: ${tc.name} → ${perm.behavior}${perm.reason ? ` (${perm.reason})` : ""}`,
        );

        if (perm.behavior === "deny") {
          const reason = `操作被拒绝: ${perm.reason}`;
          session.agentMessages.push({
            role: "tool",
            toolCallId: tc.id,
            toolName: tc.name,
            content: reason,
          });
          const ev = pub.toolDenied(tc.name, perm.reason);
          yield ev;
          events.push(ev);
          continue;
        }

        if (perm.behavior === "ask") {
          const approvalId = await createApproval(incidentId, tc, perm);
          log.info(
            `[AGENT] INTERRUPTED: approval_required, tool=${tc.name}, approvalId=${approvalId.slice(0, 8)}`,
          );
          session.status = "interrupted";
          session.pendingToolCall = tc;
          session.pendingApprovalId = approvalId;
          session.interruptedAt = new Date();
          const ev = pub.approvalRequired(
            approvalId,
            tc.name,
            tc.args,
            perm.riskLevel,
            perm.reason,
          );
          yield ev;
          events.push(ev);
          await saveSession(session, events);
          log.info(
            `[AGENT] SESSION SAVED: turn=${session.turnCount}, status=interrupted, messages=${session.agentMessages.length}`,
          );
          return; // terminalReason = "interrupted"
        }
      }

      // 执行
      log.info(`[AGENT] TOOL EXECUTING: ${tc.name}...`);
      const startEv = pub.toolStart(tc.name, tc.args);
      yield startEv;
      events.push(startEv);

      try {
        const rawResult = await toolDef.execute(tc.args);
        const output = truncateOutput(
          typeof rawResult === "string" ? rawResult : JSON.stringify(rawResult, null, 2),
          toolDef.maxResultChars,
        );
        session.agentMessages.push({
          role: "tool",
          toolCallId: tc.id,
          toolName: tc.name,
          content: output,
        });
        log.info(`[AGENT] TOOL RESULT: ${tc.name} → ${output.length} chars`);
        log.debug(`[AGENT] TOOL OUTPUT: "${output.slice(0, 300)}..."`);

        // update_plan 特殊处理
        if (tc.name === "update_plan") {
          session.planMd = (tc.args as { planMd: string }).planMd;
          const planEv = pub.planUpdated(
            (tc.args as { planMd: string }).planMd,
            (tc.args as { intent?: string }).intent,
          );
          yield planEv;
          events.push(planEv);
        }

        const resultEv = pub.toolResult(tc.name, output);
        yield resultEv;
        events.push(resultEv);
      } catch (err) {
        const errMsg = `执行失败: ${(err as Error).message}`;
        log.error(`[AGENT] TOOL ERROR: ${tc.name} → ${errMsg}`);
        session.agentMessages.push({
          role: "tool",
          toolCallId: tc.id,
          toolName: tc.name,
          content: errMsg,
        });
        const errEv = pub.toolError(tc.name, errMsg);
        yield errEv;
        events.push(errEv);
      }
    }

    // 7. 每轮双写持久化
    await saveSession(session, events);
    log.info(
      `[AGENT] SESSION SAVED: turn=${session.turnCount}, status=${session.status}, messages=${session.agentMessages.length}`,
    );
  }

  await saveSession(session);
  log.info(
    `[AGENT] ========== SESSION END ========== status=${session.status}, reason=${terminalReason}, turns=${session.turnCount}`,
  );
}
