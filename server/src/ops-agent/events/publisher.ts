import type { AgentEvent } from "../types";

export class AgentEventPublisher {
  incidentId: string;
  constructor(incidentId: string) {
    this.incidentId = incidentId;
  }

  sessionStarted(): AgentEvent {
    return { type: "session_started", data: { incidentId: this.incidentId } };
  }

  thinking(content: string): AgentEvent {
    return { type: "thinking", data: { content } };
  }

  toolStart(toolName: string, toolArgs: Record<string, unknown>): AgentEvent {
    return { type: "tool_start", data: { toolName, toolArgs } };
  }

  toolResult(toolName: string, output: string): AgentEvent {
    return { type: "tool_result", data: { toolName, output } };
  }

  toolError(toolName: string, error: string): AgentEvent {
    return { type: "tool_error", data: { toolName, error } };
  }

  toolDenied(toolName: string, reason: string): AgentEvent {
    return { type: "tool_denied", data: { toolName, reason } };
  }

  askUserQuestion(question: string): AgentEvent {
    return { type: "ask_user_question", data: { question } };
  }

  approvalRequired(
    approvalId: string,
    toolName: string,
    toolArgs: Record<string, unknown>,
    riskLevel: string,
    reason: string,
  ): AgentEvent {
    return {
      type: "approval_required",
      data: { approvalId, toolName, toolArgs, riskLevel, reason },
    };
  }

  approvalResult(approvalId: string, decision: string): AgentEvent {
    return { type: "approval_result", data: { approvalId, decision } };
  }

  compactDone(compactMd: string): AgentEvent {
    return { type: "compact_done", data: { compactMd } };
  }

  planUpdated(planMd: string, intent?: string): AgentEvent {
    return { type: "plan_updated", data: { planMd, intent } };
  }

  resumed(resumedFromTurn: number): AgentEvent {
    return { type: "resumed", data: { resumedFromTurn } };
  }

  done(finalSummary: string, totalTurns: number): AgentEvent {
    return { type: "done", data: { finalSummary, totalTurns } };
  }

  error(message: string, fatal: boolean): AgentEvent {
    return { type: "error", data: { message, fatal } };
  }
}
