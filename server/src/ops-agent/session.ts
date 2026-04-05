import { db } from "../db/connection";
import { agentSessions, messages, approvalRequests } from "../db/schema";
import { eq } from "drizzle-orm";
import type { AgentEvent, AgentSession, PermissionResult, ToolCall } from "./types";

function eventTypeToRole(eventType: string): string {
  switch (eventType) {
    case "thinking":
    case "ask_user_question":
      return "assistant";
    case "resumed":
      return "user";
    default:
      return "system";
  }
}

export async function loadOrCreateSession(incidentId: string): Promise<AgentSession> {
  const [existing] = await db
    .select()
    .from(agentSessions)
    .where(eq(agentSessions.incidentId, incidentId))
    .limit(1);

  if (existing) {
    return {
      id: existing.id,
      incidentId: existing.incidentId,
      status: existing.status as AgentSession["status"],
      agentMessages: (existing.agentMessages as AgentSession["agentMessages"]) || [],
      turnCount: existing.turnCount,
      maxTurns: existing.maxTurns,
      planMd: existing.planMd,
      compactMd: existing.compactMd,
      summary: existing.summary,
      pendingToolCall: existing.pendingToolCall as AgentSession["pendingToolCall"],
      pendingApprovalId: existing.pendingApprovalId,
      interruptedAt: existing.interruptedAt,
    };
  }

  const [created] = await db
    .insert(agentSessions)
    .values({ incidentId })
    .returning();

  return {
    id: created.id,
    incidentId: created.incidentId,
    status: "running",
    agentMessages: [],
    turnCount: 0,
    maxTurns: created.maxTurns,
    planMd: null,
    compactMd: null,
    summary: null,
    pendingToolCall: null,
    pendingApprovalId: null,
    interruptedAt: null,
  };
}

export async function loadSession(incidentId: string): Promise<AgentSession | null> {
  const [existing] = await db
    .select()
    .from(agentSessions)
    .where(eq(agentSessions.incidentId, incidentId))
    .limit(1);

  if (!existing) return null;

  return {
    id: existing.id,
    incidentId: existing.incidentId,
    status: existing.status as AgentSession["status"],
    agentMessages: (existing.agentMessages as AgentSession["agentMessages"]) || [],
    turnCount: existing.turnCount,
    maxTurns: existing.maxTurns,
    planMd: existing.planMd,
    compactMd: existing.compactMd,
    summary: existing.summary,
    pendingToolCall: existing.pendingToolCall as AgentSession["pendingToolCall"],
    pendingApprovalId: existing.pendingApprovalId,
    interruptedAt: existing.interruptedAt,
  };
}

export async function saveSession(
  session: AgentSession,
  newEvents?: AgentEvent[],
): Promise<void> {
  // 1. 更新 agent_sessions（核心状态）
  await db
    .update(agentSessions)
    .set({
      status: session.status,
      agentMessages: session.agentMessages,
      turnCount: session.turnCount,
      planMd: session.planMd,
      compactMd: session.compactMd,
      summary: session.summary,
      pendingToolCall: session.pendingToolCall,
      pendingApprovalId: session.pendingApprovalId,
      interruptedAt: session.interruptedAt,
    })
    .where(eq(agentSessions.id, session.id));

  // 2. 写入行级 messages 表（前端展示 + 审计）
  if (newEvents?.length) {
    await db.insert(messages).values(
      newEvents.map((event) => ({
        incidentId: session.incidentId,
        role: eventTypeToRole(event.type),
        eventType: event.type,
        content:
          typeof event.data === "string"
            ? event.data
            : JSON.stringify(event.data),
      })),
    );
  }
}

export async function createApproval(
  incidentId: string,
  toolCall: ToolCall,
  perm: PermissionResult,
): Promise<string> {
  const [approval] = await db
    .insert(approvalRequests)
    .values({
      incidentId,
      toolName: toolCall.name,
      toolArgs: JSON.stringify(toolCall.args),
      riskLevel: perm.riskLevel || null,
      riskDetail: perm.reason || null,
    })
    .returning();

  return approval.id;
}
