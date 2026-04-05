import type { z } from "zod";

// ─── LLM Messages ───────────────────────────────────────

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export type MessageRole = "system" | "user" | "assistant" | "tool";

export type Message =
  | { role: "system"; content: string }
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; toolCalls?: ToolCall[] }
  | { role: "tool"; toolCallId: string; toolName: string; content: string };

// ─── Permission ─────────────────────────────────────────

export type CommandType = "read" | "write" | "dangerous" | "blocked";

export type PermissionBehavior = "allow" | "ask" | "deny";

export interface PermissionResult {
  behavior: PermissionBehavior;
  reason: string;
  riskLevel: "MEDIUM" | "HIGH" | "";
}

// ─── Tool ───────────────────────────────────────────────

export interface ToolDefinition<TArgs = unknown> {
  name: string;
  description: string;
  parameters: z.ZodType<TArgs>;
  needsPermissionCheck: boolean;
  maxResultChars: number;
  checkPermission?: (args: TArgs) => Promise<PermissionResult>;
  execute: (args: TArgs) => Promise<unknown>;
}

// ─── Agent Session ──────────────────────────────────────

export type SessionStatus = "running" | "interrupted" | "completed" | "failed";

export interface AgentSession {
  id: string;
  incidentId: string;
  status: SessionStatus;
  agentMessages: Message[];
  turnCount: number;
  maxTurns: number;
  planMd: string | null;
  compactMd: string | null;
  summary: string | null;
  pendingToolCall: ToolCall | null;
  pendingApprovalId: string | null;
  interruptedAt: Date | null;
}

// ─── Agent Events (SSE) ────────────────────────────────

export type AgentEvent =
  | { type: "session_started"; data: { incidentId: string } }
  | { type: "thinking"; data: { content: string } }
  | { type: "tool_start"; data: { toolName: string; toolArgs: Record<string, unknown> } }
  | { type: "tool_result"; data: { toolName: string; output: string } }
  | { type: "tool_error"; data: { toolName: string; error: string } }
  | { type: "tool_denied"; data: { toolName: string; reason: string } }
  | { type: "ask_user_question"; data: { question: string } }
  | {
      type: "approval_required";
      data: {
        approvalId: string;
        toolName: string;
        toolArgs: Record<string, unknown>;
        riskLevel: string;
        reason: string;
      };
    }
  | { type: "approval_result"; data: { approvalId: string; decision: string } }
  | { type: "plan_updated"; data: { planMd: string; intent?: string } }
  | { type: "compact_done"; data: { compactMd: string } }
  | { type: "resumed"; data: { resumedFromTurn: number } }
  | { type: "done"; data: { finalSummary: string; totalTurns: number } }
  | { type: "error"; data: { message: string; fatal: boolean } };

// ─── Resume Input ──────────────────────────────────────

export type ResumeInput =
  | { type: "approval"; decision: "approved" | "rejected"; feedback?: string }
  | { type: "human_input"; text: string }
  | { type: "confirm"; confirmed: boolean; text?: string };

// ─── Executor ──────────────────────────────────────────

export type Executor = (
  connectionInfo: Record<string, unknown>,
  operation: string,
  params: Record<string, unknown>,
) => Promise<unknown>;
