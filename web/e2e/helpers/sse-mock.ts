import type { Route } from "@playwright/test";
import type { SSEEvent } from "../../src/lib/types";
import { APPROVAL_ID, APPROVAL_ID_OOM } from "./mock-data";

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

// ── 用例 1：PostgreSQL 连接池耗尽（纯读诊断） ──

export function createDbDiagnosticEvents(): SSEEvent[] {
  const ts = "2026-03-16T10:00:30Z";
  const ts2 = "2026-03-16T10:01:00Z";
  return [
    // gather_context phase
    {
      event_type: "thinking",
      data: {
        content: "正在搜索数据库连接池相关的历史事件...",
        phase: "gather_context",
        agent: "history",
      },
      timestamp: ts,
    },
    {
      event_type: "tool_call",
      data: {
        name: "search_incident_history",
        args: { query: "PostgreSQL 连接池耗尽 too many clients" },
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
          "找到2条相似历史事件：1) PostgreSQL max_connections 不足 — 扩容解决  2) 连接泄漏导致连接池耗尽 — 应用重启",
        phase: "gather_context",
        agent: "history",
      },
      timestamp: ts,
    },
    // main_agent phase — step 1: check pg_stat_activity
    {
      event_type: "thinking",
      data: { content: "需要检查 PostgreSQL 当前的连接状态，查看活跃连接数。" },
      timestamp: ts2,
    },
    {
      event_type: "tool_call",
      data: {
        name: "exec_read_tool",
        args: { command: "psql -U postgres -c \"SELECT state, count(*) FROM pg_stat_activity GROUP BY state;\"" },
      },
      timestamp: ts2,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_read_tool",
        output:
          " state  | count\n--------+-------\n active |    95\n idle   |     3\n        |     2\n(3 rows)",
      },
      timestamp: ts2,
    },
    // main_agent phase — step 2: check max_connections
    {
      event_type: "thinking",
      data: { content: "95个活跃连接，需要确认 max_connections 配置值。" },
      timestamp: ts2,
    },
    {
      event_type: "tool_call",
      data: {
        name: "exec_read_tool",
        args: { command: "psql -U postgres -c \"SHOW max_connections;\"" },
      },
      timestamp: ts2,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_read_tool",
        output: " max_connections\n-----------------\n 100\n(1 row)",
      },
      timestamp: ts2,
    },
    // main_agent phase — step 3: check long-running queries
    {
      event_type: "thinking",
      data: { content: "max_connections=100，已用95个。检查是否有长时间运行的查询占用连接。" },
      timestamp: ts2,
    },
    {
      event_type: "tool_call",
      data: {
        name: "exec_read_tool",
        args: {
          command:
            "psql -U postgres -c \"SELECT pid, now()-query_start AS duration, query FROM pg_stat_activity WHERE state='active' AND now()-query_start > interval '5 minutes' ORDER BY duration DESC LIMIT 5;\"",
        },
      },
      timestamp: ts2,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_read_tool",
        output:
          "  pid  |  duration   |                    query\n-------+-------------+---------------------------------------------\n 12345 | 00:47:23.12 | SELECT * FROM orders WHERE created_at > ...\n 12346 | 00:32:11.45 | UPDATE inventory SET stock = stock - 1 ...\n(2 rows)",
      },
      timestamp: ts2,
    },
    // main_agent phase — step 4: check application health
    {
      event_type: "thinking",
      data: { content: "发现2条慢查询。再检查应用端的健康状态确认影响范围。" },
      timestamp: ts2,
    },
    {
      event_type: "tool_call",
      data: {
        name: "http_request_tool",
        args: { method: "GET", url: "http://app-server:8080/health" },
      },
      timestamp: ts2,
    },
    {
      event_type: "tool_result",
      data: {
        name: "http_request_tool",
        output:
          'HTTP 503 Service Unavailable\n{"status":"unhealthy","database":"pool exhausted","error":"too many clients already","active_connections":95,"max_connections":100}',
      },
      timestamp: ts2,
    },
    // main_agent phase — conclusion
    {
      event_type: "thinking",
      data: {
        content:
          "诊断完成：max_connections=100 配置过低，95个活跃连接中有2条慢查询占用资源，导致连接池耗尽。应用健康检查返回503。建议：1) 终止慢查询释放连接 2) 调整 max_connections 配置 3) 排查应用连接泄漏问题。",
      },
      timestamp: ts2,
    },
    // summary
    {
      event_type: "summary",
      data: {
        summary_md:
          "## 排查报告\n\n### 问题\n应用返回 503，PostgreSQL 报错 too many clients already。\n\n### 根因\n- `max_connections` 设置为 100，当前已有 95 个活跃连接\n- 存在 2 条运行超过 30 分钟的慢查询占用连接\n- 连接池耗尽导致新请求无法获取数据库连接\n\n### 建议\n1. 终止长时间运行的慢查询释放连接\n2. 将 `max_connections` 从 100 调整到 300\n3. 排查应用侧连接池配置，确认是否存在连接泄漏",
      },
      timestamp: ts2,
    },
  ];
}

// ── 用例 2：Cron Job OOM Kill（审批流程） ──

export function createOomPreApprovalEvents(): SSEEvent[] {
  const ts = "2026-03-16T10:00:30Z";
  const ts2 = "2026-03-16T10:01:00Z";
  return [
    // gather_context phase
    {
      event_type: "thinking",
      data: {
        content: "正在搜索 OOM 相关的历史事件...",
        phase: "gather_context",
        agent: "history",
      },
      timestamp: ts,
    },
    {
      event_type: "tool_call",
      data: {
        name: "search_incident_history",
        args: { query: "OOM killer cron-worker 内存不足" },
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
          "找到1条相似历史事件：cron-worker OOM Kill — 增大内存限制后恢复",
        phase: "gather_context",
        agent: "history",
      },
      timestamp: ts,
    },
    // main_agent phase — step 1: check dmesg
    {
      event_type: "thinking",
      data: { content: "检查系统日志确认 OOM killer 事件详情。" },
      timestamp: ts2,
    },
    {
      event_type: "tool_call",
      data: {
        name: "exec_read_tool",
        args: { command: "dmesg | grep -i 'oom\\|killed' | tail -5" },
      },
      timestamp: ts2,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_read_tool",
        output:
          "[Mon Mar 16 09:45:12 2026] Out of memory: Killed process 8234 (cron-worker) total-vm:2048000kB, anon-rss:1048576kB\n[Mon Mar 16 09:45:12 2026] oom_reaper: reaped process 8234 (cron-worker)",
      },
      timestamp: ts2,
    },
    // main_agent phase — step 2: check memory + service status
    {
      event_type: "thinking",
      data: { content: "确认 cron-worker 被 OOM killer 终止。检查当前内存状态和服务状态。" },
      timestamp: ts2,
    },
    {
      event_type: "tool_call",
      data: {
        name: "exec_read_tool",
        args: { command: "free -h && echo '---' && systemctl status cron-worker" },
      },
      timestamp: ts2,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_read_tool",
        output:
          "              total        used        free\nMem:           3.8G        3.2G        0.6G\nSwap:            0B          0B          0B\n---\n● cron-worker.service - Cron Worker Service\n   Active: failed (Result: signal)\n   Main PID: 8234 (code=killed, signal=KILL)",
      },
      timestamp: ts2,
    },
    // main_agent phase — step 3: check systemd config
    {
      event_type: "thinking",
      data: { content: "服务已失败。检查 systemd 的内存限制配置。" },
      timestamp: ts2,
    },
    {
      event_type: "tool_call",
      data: {
        name: "exec_read_tool",
        args: { command: "cat /etc/systemd/system/cron-worker.service | grep -i memory" },
      },
      timestamp: ts2,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_read_tool",
        output: "MemoryLimit=1G",
      },
      timestamp: ts2,
    },
    // main_agent phase — decision: need write operation
    {
      event_type: "thinking",
      data: {
        content:
          "MemoryLimit=1G 太低，cron-worker 实际使用了约 1GB 被 OOM kill。需要增大内存限制到 3G 并重启服务。这是写操作，需要审批。",
      },
      timestamp: ts2,
    },
    // approval_required
    {
      event_type: "approval_required",
      data: {
        tool_args: {
          command:
            "sed -i 's/MemoryLimit=1G/MemoryLimit=3G/' /etc/systemd/system/cron-worker.service && systemctl daemon-reload && systemctl restart cron-worker",
          risk_level: "MEDIUM",
          explanation: "增大 cron-worker 内存限制从 1G 到 3G 并重启服务",
          risk_detail:
            "修改 systemd 配置文件并重启服务，服务会短暂中断。如果 cron-worker 正在处理任务，任务将被中断。",
        },
        approval_id: APPROVAL_ID_OOM,
      },
      timestamp: ts2,
    },
  ];
}

export function createOomResumeEvents(): SSEEvent[] {
  const ts = "2026-03-16T10:05:00Z";
  return [
    // write operation executed
    {
      event_type: "tool_call",
      data: {
        name: "exec_write_tool",
        args: {
          command:
            "sed -i 's/MemoryLimit=1G/MemoryLimit=3G/' /etc/systemd/system/cron-worker.service && systemctl daemon-reload && systemctl restart cron-worker",
        },
      },
      timestamp: ts,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_write_tool",
        output: "配置已更新，服务重启成功",
      },
      timestamp: ts,
    },
    // verification step
    {
      event_type: "thinking",
      data: { content: "写操作完成，验证配置是否生效以及服务是否正常运行。" },
      timestamp: ts,
    },
    {
      event_type: "tool_call",
      data: {
        name: "exec_read_tool",
        args: {
          command:
            "grep MemoryLimit /etc/systemd/system/cron-worker.service && systemctl status cron-worker",
        },
      },
      timestamp: ts,
    },
    {
      event_type: "tool_result",
      data: {
        name: "exec_read_tool",
        output:
          "MemoryLimit=3G\n● cron-worker.service - Cron Worker Service\n   Active: active (running) since Mon 2026-03-16 10:05:03 UTC\n   Main PID: 9012\n   Memory: 245.0M",
      },
      timestamp: ts,
    },
    // conclusion
    {
      event_type: "thinking",
      data: { content: "配置已更新为 MemoryLimit=3G，服务已恢复运行，内存使用正常。" },
      timestamp: ts,
    },
    // summary
    {
      event_type: "summary",
      data: {
        summary_md:
          "## 排查报告\n\n### 问题\ncron-worker 被 OOM killer 终止，服务不可用。\n\n### 根因\nsystemd 配置 `MemoryLimit=1G` 过低，cron-worker 实际内存使用超过 1G 触发 OOM killer。\n\n### 处理\n1. 将 `MemoryLimit` 从 1G 调整到 3G\n2. 执行 `systemctl daemon-reload && systemctl restart cron-worker`\n3. 验证服务已恢复运行，当前内存使用 245MB\n\n### 建议\n- 监控 cron-worker 内存使用趋势\n- 考虑优化任务的内存占用",
      },
      timestamp: ts,
    },
  ];
}
