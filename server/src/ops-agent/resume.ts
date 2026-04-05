import type { AgentEvent, ResumeInput } from "./types";
import { AgentEventPublisher } from "./events/publisher";
import { truncateOutput } from "./context/truncation";
import { loadSession, saveSession } from "./session";
import { getToolByName } from "./tools/registry";
import { runAgent } from "./agent-loop";

export async function* resumeAgent(
  incidentId: string,
  input: ResumeInput,
): AsyncGenerator<AgentEvent> {
  const session = await loadSession(incidentId);
  if (!session) {
    throw new Error(`No agent session found for incident: ${incidentId}`);
  }

  const pub = new AgentEventPublisher(incidentId);
  yield pub.resumed(session.turnCount);

  switch (input.type) {
    case "approval": {
      const tc = session.pendingToolCall;
      if (!tc) throw new Error("No pending tool call to resume");

      if (input.decision === "approved") {
        const toolDef = getToolByName(tc.name);
        if (!toolDef) throw new Error(`Tool not found: ${tc.name}`);

        const startEv = pub.toolStart(tc.name, tc.args);
        yield startEv;

        try {
          const rawResult = await toolDef.execute(tc.args);
          const output = truncateOutput(
            typeof rawResult === "string" ? rawResult : JSON.stringify(rawResult, null, 2),
            toolDef.maxResultChars,
          );
          session.agentMessages.push({ role: "tool", toolCallId: tc.id, toolName: tc.name, content: output });
          yield pub.toolResult(tc.name, output);
        } catch (err) {
          const errMsg = `执行失败: ${(err as Error).message}`;
          session.agentMessages.push({ role: "tool", toolCallId: tc.id, toolName: tc.name, content: errMsg });
          yield pub.toolError(tc.name, errMsg);
        }
      } else {
        const msg = `用户拒绝操作${input.feedback ? ": " + input.feedback : ""}`;
        session.agentMessages.push({ role: "tool", toolCallId: tc.id, toolName: tc.name, content: msg });
      }

      yield pub.approvalResult(session.pendingApprovalId || "", input.decision);
      break;
    }

    case "human_input": {
      session.agentMessages.push({ role: "user", content: input.text });
      break;
    }

    case "confirm": {
      if (input.confirmed) {
        session.status = "completed";
        yield pub.done(session.summary || "", session.turnCount);
        await saveSession(session);
        return;
      }
      session.agentMessages.push({
        role: "user",
        content: `[问题未解决] ${input.text || "请继续排查"}`,
      });
      break;
    }
  }

  // 清除中断状态
  session.status = "running";
  session.pendingToolCall = null;
  session.pendingApprovalId = null;
  session.interruptedAt = null;
  await saveSession(session);

  // 继续主循环
  yield* runAgent(incidentId);
}
