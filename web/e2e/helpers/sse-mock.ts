import type { Route } from "@playwright/test";
import type { SSEEvent } from "../../src/lib/types";
import { APPROVAL_ID } from "./mock-data";

export function encodeSSEStream(
  events: SSEEvent[],
  options?: { retryMs?: number },
): string {
  const prefix = options?.retryMs != null ? `retry: ${options.retryMs}\n\n` : "";
  return prefix + events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

export async function fulfillSSE(
  route: Route,
  events: SSEEvent[],
  options?: { retryMs?: number },
) {
  await route.fulfill({
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
    body: encodeSSEStream(events, options),
  });
}

// ── Event Factories ──

export function createGatherContextEvents(): SSEEvent[] {
  const ts = "2026-03-16T10:00:30Z";
  return [
    {
      event_type: "thinking",
      data: {
        content: "正在搜索相似的历史事件...",
        phase: "gather_context",
        agent: "history",
      },
      timestamp: ts,
    },
    {
      event_type: "tool_call",
      data: {
        name: "search_incident_history",
        args: { query: "Nginx 502 错误" },
        phase: "gather_context",
        agent: "history",
      },
      timestamp: ts,
    },
    {
      event_type: "tool_result",
      data: {
        name: "search_incident_history",
        output:
          "找到1条相似历史事件：Nginx 502 Bad Gateway — 上游服务崩溃",
        phase: "gather_context",
        agent: "history",
      },
      timestamp: ts,
    },
  ];
}

export function createMainAgentEvents(): SSEEvent[] {
  const ts = "2026-03-16T10:01:00Z";
  return [
    {
      event_type: "thinking",
      data: { content: "让我分析这个问题，需要检查服务器的 Nginx 服务状态。" },
      timestamp: ts,
    },
    {
      event_type: "tool_call",
      data: {
        name: "exec_read_tool",
        args: { command: "systemctl status nginx" },
      },
      timestamp: ts,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_read_tool",
        output:
          "● nginx.service - A high performance web server\n   Active: failed (Result: exit-code)\n   Process: 1234 ExecStart=/usr/sbin/nginx (code=exited, status=1/FAILURE)",
      },
      timestamp: ts,
    },
    {
      event_type: "thinking",
      data: { content: "Nginx 服务已停止，需要重启，这需要审批。" },
      timestamp: ts,
    },
    {
      event_type: "approval_required",
      data: {
        tool_args: {
          command: "systemctl restart nginx",
          risk_level: "MEDIUM",
          explanation: "重启 Nginx 服务以恢复 Web 服务",
          risk_detail: "服务重启期间会有短暂的请求中断",
        },
        approval_id: APPROVAL_ID,
      },
      timestamp: ts,
    },
  ];
}

/** All pre-approval events (gather_context + main agent up to approval) */
export function createAgentFlowEvents(): SSEEvent[] {
  return [...createGatherContextEvents(), ...createMainAgentEvents()];
}

/** Events that come AFTER approval (write tool execution + summary) */
export function createResumeEvents(): SSEEvent[] {
  const ts = "2026-03-16T10:05:00Z";
  return [
    {
      event_type: "tool_call",
      data: {
        name: "exec_write_tool",
        args: { command: "systemctl restart nginx" },
      },
      timestamp: ts,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_write_tool",
        output:
          "● nginx.service - A high performance web server\n   Active: active (running) since Mon 2026-03-16 10:05:01 UTC",
      },
      timestamp: ts,
    },
    {
      event_type: "summary",
      data: {
        summary_md:
          "## 排查报告\n\n### 问题\nNginx 服务异常导致 502 错误。\n\n### 原因\n服务进程异常退出。\n\n### 处理\n已成功重启 Nginx 服务，服务恢复正常运行。",
      },
      timestamp: ts,
    },
  ];
}

/** Full event sequence including post-approval (for static fulfill) */
export function createPostApprovalEvents(): SSEEvent[] {
  return [...createAgentFlowEvents(), ...createResumeEvents()];
}

export function createErrorEvents(): SSEEvent[] {
  return [
    {
      event_type: "error",
      data: { message: "Agent 执行过程中发生错误：连接超时" },
      timestamp: "2026-03-16T10:01:00Z",
    },
  ];
}
