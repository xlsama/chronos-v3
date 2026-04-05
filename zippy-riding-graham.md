# Chronos V3 Ops AI Agent 设计方案

## Context

从零设计一个纯 `while` 循环 + messages 驱动的 Ops AI Agent。参考 Claude Code 的 `queryLoop()` 核心模式，不依赖任何框架。

---

## 一、核心架构：单 while 循环 + Messages 驱动

### 1.1 设计原则

1. 整个 Agent 就是一个 `while(true)` 循环
2. 状态 = messages 数组，所有上下文、工具结果、用户回复都是 messages
3. LLM 决定一切：调什么工具、什么时候结束、什么时候问用户
4. 循环只做三件事：调 LLM → 执行工具 → 结果追加到 messages → 继续
5. 没有工具调用 = 任务完成

### 1.2 流转图

```
事件触发（用户提问/告警/截图）
    │
    ▼
┌══════════════════════════════════════════════════════════════┐
║ runAgent(incidentId) —— while(true)                         ║
║                                                              ║
║  ① compact 检查（messages 过长时压缩）                        ║
║                         │                                    ║
║  ② 调用 LLM（streamText + tools）                            ║
║     → 收集 assistantMessage + toolCalls                      ║
║                         │                                    ║
║  ③ 没有 toolCalls?                                           ║
║     YES → status = 'completed', break                        ║
║     NO  ↓                                                    ║
║                                                              ║
║  ④ 遍历 toolCalls，逐个执行:                                  ║
║     ├─ service_exec       → 权限检查 → 执行/审批中断          ║
║     ├─ ask_user_question  → yield 问题, interrupt            ║
║     ├─ update_plan        → 更新计划到 DB                    ║
║     └─ 其他只读工具        → 直接执行                         ║
║                         │                                    ║
║     如果需要审批:                                             ║
║       → 双写持久化                                            ║
║       → status = 'interrupted'                               ║
║       → return（等待 resume）                                 ║
║                         │                                    ║
║  ⑤ 工具结果追加到 messages                                    ║
║     → 双写持久化                                              ║
║     → continue 回到 ①                                        ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 二、数据库设计

### 2.1 核心思路：双写模式

| 表 | 存储内容 | 用途 | 读写频率 | 数据格式 |
|----|---------|------|---------|---------|
| `agent_sessions` | agentMessages (JSONB) | Agent 运行时状态（LLM 上下文） | 每轮循环读写一次 | 整个 Message[] 数组 |
| `messages` (行级表) | 每条事件单独一行 | 前端展示 + 审计 + 日志 | 每条事件写一次 | 结构化行记录 |

- `agent_sessions.agentMessages` = Agent 真正的状态，中断恢复完全靠它
- `messages` 行表 = 前端时间线展示、按类型过滤、搜索、导出日志

### 2.2 agent_sessions 表

```typescript
export const agentSessions = pgTable(
  "agent_sessions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    incidentId: uuid("incident_id")
      .notNull()
      .references(() => incidents.id, { onDelete: "cascade" })
      .unique(),

    status: varchar("status", { length: 20 }).notNull().default("running"),
    // running | interrupted | completed | failed

    // ═══ 核心状态 ═══
    agentMessages: jsonb("agent_messages").notNull().default([]),
    turnCount: integer("turn_count").notNull().default(0),
    maxTurns: integer("max_turns").notNull().default(40),

    // ═══ Plan & Compact ═══
    planMd: text("plan_md"),
    compactMd: text("compact_md"),
    summary: text("summary"), // Agent 完成后的最终总结，前端快速展示

    // ═══ 中断恢复 ═══
    pendingToolCall: jsonb("pending_tool_call"), // { id, name, args }
    pendingApprovalId: uuid("pending_approval_id"),
    interruptedAt: timestamp("interrupted_at", { withTimezone: true }),

    // ═══ 时间戳 ═══
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow()
      .$onUpdate(() => new Date()),
  },
  (table) => [
    index("ix_agent_sessions_incident_id").on(table.incidentId),
    index("ix_agent_sessions_status").on(table.status),
  ],
);
```

### 2.3 双写实现

```typescript
async function saveSession(session: AgentSession, newEvents?: AgentEvent[]) {
  // 1. 更新 Agent 运行状态（核心）
  await db.update(agentSessions)
    .set({
      agentMessages: session.agentMessages,
      status: session.status,
      turnCount: session.turnCount,
      pendingToolCall: session.pendingToolCall,
      pendingApprovalId: session.pendingApprovalId,
      planMd: session.planMd,
      summary: session.summary,
    })
    .where(eq(agentSessions.id, session.id));

  // 2. 写入行级消息表（用于前端展示）
  if (newEvents?.length) {
    await db.insert(messages).values(
      newEvents.map(event => ({
        incidentId: session.incidentId,
        role: event.role || "system",
        eventType: event.type,
        content: typeof event.data === "string" ? event.data : JSON.stringify(event.data),
        metadataJson: event.metadata,
      }))
    );
  }
}
```

---

## 三、runAgent 核心实现

```typescript
async function* runAgent(
  incidentId: string,
  initialPrompt?: string,
): AsyncGenerator<AgentEvent> {
  let session = await loadOrCreateSession(incidentId);
  if (initialPrompt) {
    session.agentMessages.push({ role: "user", content: initialPrompt });
  }

  const tools = buildToolRegistry();
  yield { type: "session_started", data: { incidentId } };

  while (true) {
    // 1. 防死循环
    session.turnCount++;
    if (session.turnCount > session.maxTurns) {
      yield { type: "error", data: { message: "达到最大循环次数", fatal: true } };
      session.status = "failed";
      break;
    }

    // 2. 调用 LLM
    const llmResult = yield* callLLM({
      system: buildSystemPrompt(session),
      messages: session.agentMessages,
      tools: tools.map(t => t.definition),
    });

    // 3. 记录 assistant 回复
    session.agentMessages.push(llmResult.assistantMessage);

    // 4. 没有 tool call → 完成
    if (!llmResult.toolCalls?.length) {
      session.status = "completed";
      session.summary = llmResult.assistantMessage.content;
      yield { type: "done", data: { finalSummary: session.summary, totalTurns: session.turnCount } };
      break;
    }

    // 5. 执行工具
    const newEvents: AgentEvent[] = [];

    for (const tc of llmResult.toolCalls) {
      const tool = tools.find(t => t.name === tc.name);
      if (!tool) {
        const errMsg = `未知工具: ${tc.name}`;
        session.agentMessages.push({ role: "tool", toolCallId: tc.id, content: errMsg });
        newEvents.push({ type: "tool_error", data: { toolName: tc.name, error: errMsg } });
        continue;
      }

      // 权限检查
      if (tool.needsPermissionCheck) {
        const perm = await tool.checkPermission(tc.args);

        if (perm.behavior === "deny") {
          const reason = `操作被拒绝: ${perm.reason}`;
          session.agentMessages.push({ role: "tool", toolCallId: tc.id, content: reason });
          newEvents.push({ type: "tool_denied", data: { toolName: tc.name, reason: perm.reason } });
          continue;
        }

        if (perm.behavior === "ask") {
          const approvalId = await createApproval(incidentId, tc, perm);
          session.status = "interrupted";
          session.pendingToolCall = tc;
          session.pendingApprovalId = approvalId;
          session.interruptedAt = new Date();
          yield { type: "approval_required", data: { approvalId, toolName: tc.name, toolArgs: tc.args, riskLevel: perm.riskLevel, reason: perm.reason } };
          await saveSession(session, newEvents);
          return;
        }
      }

      // 执行
      const startEvent: AgentEvent = { type: "tool_start", data: { toolName: tc.name, toolArgs: tc.args } };
      yield startEvent;
      newEvents.push(startEvent);

      try {
        const result = await tool.execute(tc.args);
        const output = truncateOutput(String(result), tool.maxResultChars);
        session.agentMessages.push({ role: "tool", toolCallId: tc.id, content: output });

        // 特殊处理：update_plan
        if (tc.name === "update_plan") {
          session.planMd = tc.args.planMd;
          newEvents.push({ type: "plan_updated", data: { planMd: tc.args.planMd, intent: tc.args.intent } });
        }

        const resultEvent: AgentEvent = { type: "tool_result", data: { toolName: tc.name, output } };
        yield resultEvent;
        newEvents.push(resultEvent);
      } catch (err) {
        const errMsg = `执行失败: ${err.message}`;
        session.agentMessages.push({ role: "tool", toolCallId: tc.id, content: errMsg });
        const errorEvent: AgentEvent = { type: "tool_error", data: { toolName: tc.name, error: errMsg } };
        yield errorEvent;
        newEvents.push(errorEvent);
      }
    }

    // 6. 每轮双写持久化
    await saveSession(session, newEvents);
  }

  await saveSession(session);
}
```

### 3.1 resumeAgent

```typescript
async function* resumeAgent(
  incidentId: string,
  input: ResumeInput,
): AsyncGenerator<AgentEvent> {
  const session = await loadSession(incidentId);
  yield { type: "resumed", data: { resumedFromTurn: session.turnCount } };

  switch (input.type) {
    case "approval": {
      const tc = session.pendingToolCall!;
      if (input.decision === "approved") {
        const tool = getToolByName(tc.name);
        const result = await tool.execute(tc.args);
        session.agentMessages.push({
          role: "tool", toolCallId: tc.id,
          content: truncateOutput(String(result), tool.maxResultChars),
        });
        yield { type: "tool_result", data: { toolName: tc.name, output: String(result) } };
      } else {
        session.agentMessages.push({
          role: "tool", toolCallId: tc.id,
          content: `用户拒绝操作${input.feedback ? ": " + input.feedback : ""}`,
        });
      }
      yield { type: "approval_result", data: { approvalId: session.pendingApprovalId, decision: input.decision } };
      break;
    }

    case "human_input":
      session.agentMessages.push({ role: "user", content: input.text });
      break;

    case "confirm":
      if (input.confirmed) {
        session.status = "completed";
        yield { type: "done", data: { finalSummary: session.summary, totalTurns: session.turnCount, success: true } };
        await saveSession(session);
        return;
      }
      session.agentMessages.push({ role: "user", content: `[问题未解决] ${input.text || ""}` });
      break;
  }

  session.status = "running";
  session.pendingToolCall = null;
  session.pendingApprovalId = null;
  await saveSession(session);

  yield* runAgent(incidentId);
}
```

---

## 四、Tool 系统

### 4.1 命名规范

Tool name 使用 snake_case（LLM function calling 通用习惯）：

| Tool | 说明 | 权限检查 |
|------|------|---------|
| `service_exec` | 核心 Tool，执行所有 Service 操作 | 危险词判断 |
| `ask_user_question` | 向用户提问，中断等回复 | 无 |
| `update_plan` | 创建/更新调查计划（Phase 2） | 无 |
| `search_knowledge` | 向量搜索项目知识库（Phase 2） | 无 |
| `search_incidents` | 搜索历史类似事件（Phase 2） | 无 |
| `ssh_bash` | SSH 到远程服务器执行命令（Phase 3） | ShellSafety |
| `bash` | 本地执行命令（Phase 3） | ShellSafety |

**注意**：`list_servers` / `list_services` 不做独立 Tool，在 system prompt 中自动注入。

### 4.2 ToolDefinition 接口

```typescript
interface ToolDefinition {
  name: string;
  description: string;
  parameters: z.ZodType;
  needsPermissionCheck: boolean;
  maxResultChars: number;
  checkPermission?: (args: unknown) => Promise<PermissionResult>;
  execute: (args: unknown) => Promise<unknown>;
}
```

### 4.3 service_exec — 核心 Tool

```typescript
const serviceExecTool: ToolDefinition = {
  name: "service_exec",
  description: "执行预注册的 Service 操作（Docker/K8s/MySQL/PostgreSQL/MongoDB）。所有操作通过结构化参数执行。",
  parameters: z.object({
    serviceId: z.string().describe("Service ID"),
    operation: z.string().describe("操作名: listContainers, executeSql, findDocuments 等"),
    parameters: z.record(z.any()).optional().describe("操作参数"),
  }),
  needsPermissionCheck: true,
  maxResultChars: 30_000,

  async checkPermission(args) {
    // MVP: 简单危险词判断
    const dangerousOps = ["delete", "remove", "drop", "kill", "restart", "stop", "truncate"];
    const op = args.operation.toLowerCase();
    if (dangerousOps.some(d => op.includes(d))) {
      return { behavior: "ask", reason: `高风险操作: ${args.operation}`, riskLevel: "HIGH" };
    }
    return { behavior: "allow", reason: "", riskLevel: "" };
  },

  async execute(args) {
    return executeService(args.serviceId, args.operation, args.parameters);
  },
};
```

### 4.4 update_plan

```typescript
const updatePlanTool: ToolDefinition = {
  name: "update_plan",
  description: "创建或更新调查计划。首次调用为创建，后续调用为更新。",
  parameters: z.object({
    planMd: z.string().describe("Markdown 格式的调查计划"),
    intent: z.enum(["incident", "question", "task"]).optional().describe("事件意图（首次创建时填）"),
  }),
  needsPermissionCheck: false,
  maxResultChars: 1000,
  async execute(args) {
    return "计划已更新。";
  },
};
```

### 4.5 Executor Registry

```typescript
const executors: Record<string, Executor> = {
  docker: dockerExecutor,      // dockerode
  kubernetes: k8sExecutor,     // @kubernetes/client-node
  mysql: sqlExecutor,          // bun:sql
  postgresql: sqlExecutor,     // bun:sql
  mongodb: mongoExecutor,      // mongodb
};

async function executeService(serviceId: string, operation: string, params: any) {
  const service = await db.services.findById(serviceId);
  const executor = executors[service.serviceType];
  if (!executor) throw new Error(`不支持的 Service Type: ${service.serviceType}`);
  return executor(service, operation, params);
}
```

---

## 五、SSE 事件系统

### 5.1 事件格式

```typescript
interface AgentEvent {
  type: string;
  data?: unknown;
  metadata?: Record<string, unknown>;
}
```

### 5.2 MVP 核心事件（8 个）

| 事件 | 说明 | data |
|------|------|------|
| `thinking` | LLM 流式思考 | `{ content: string }` |
| `tool_start` | 准备执行工具 | `{ toolName, toolArgs }` |
| `tool_result` | 工具执行成功 | `{ toolName, output }` |
| `tool_error` | 工具执行失败 | `{ toolName, error }` |
| `ask_user_question` | Agent 向用户提问 | `{ question }` |
| `approval_required` | 高风险操作需审批 | `{ approvalId, toolName, toolArgs, riskLevel, reason }` |
| `done` | Agent 完成 | `{ finalSummary, totalTurns }` |
| `error` | 严重错误 | `{ message, fatal }` |

### 5.3 完整事件（后续补充）

| 事件 | 说明 |
|------|------|
| `session_started` | Agent 会话开始 |
| `tool_denied` | 权限拒绝 |
| `approval_result` | 审批结果 |
| `plan_updated` | 计划更新 |
| `compact_done` | 上下文压缩完成 |
| `resumed` | 从中断恢复 |
| `interrupted` | 被中断 |
| `heartbeat` | 保活（每 15s） |

### 5.4 EventPublisher

```typescript
class AgentEventPublisher {
  constructor(private incidentId: string) {}

  emitThinking(content: string): AgentEvent;
  emitToolStart(toolName: string, args: unknown): AgentEvent;
  emitToolResult(toolName: string, output: string): AgentEvent;
  emitToolError(toolName: string, error: string): AgentEvent;
  emitAskUserQuestion(question: string): AgentEvent;
  emitApprovalRequired(approvalId: string, toolName: string, toolArgs: unknown, riskLevel: string, reason: string): AgentEvent;
  emitDone(summary: string, totalTurns: number): AgentEvent;
  emitError(message: string, fatal: boolean): AgentEvent;
}
```

### 5.5 API 端点

```typescript
POST /api/incidents/:id/run    → SSE stream (runAgent)
POST /api/incidents/:id/resume → SSE stream (resumeAgent)
```

---

## 六、System Prompt（MVP 版）

```
你是一个专业的运维 Ops AI Agent。
收到用户请求后：
1. 先思考需要哪些信息。
2. 如果信息不足，使用 ask_user_question 向用户提问。
3. 使用 service_exec 工具执行所有 Docker、Kubernetes、数据库操作，绝不要输出 shell 命令。
4. 操作前如果属于高危操作（包含 delete/remove/drop/kill/restart），必须先询问用户。
5. 完成后输出清晰总结，不要再调用任何工具。
```

---

## 七、目录结构

```
server/src/ops-agent/
├── index.ts                      # 公共 API: runAgent, resumeAgent
├── types.ts                      # Message, ToolCall, AgentEvent, PermissionResult
├── agent-loop.ts                 # runAgent 主循环
├── resume.ts                     # resumeAgent
│
├── tools/
│   ├── registry.ts               # buildToolRegistry(), ToolDefinition
│   ├── service-exec.ts           # service_exec
│   ├── ask-user-question.ts      # ask_user_question
│   ├── update-plan.ts            # update_plan (Phase 2)
│   ├── search-knowledge.ts       # search_knowledge (Phase 2)
│   ├── search-incidents.ts       # search_incidents
│   ├── ssh-bash.ts               # ssh_bash
│   └── bash.ts                   # bash
│
├── executors/
│   ├── registry.ts               # executeService()
│   ├── docker.ts                 # dockerode
│   ├── kubernetes.ts             # @kubernetes/client-node
│   ├── sql.ts                    # bun:sql (MySQL + PostgreSQL)
│   └── mongodb.ts                # mongodb
│
├── safety/
│   ├── shell-classifier.ts       # ShellSafety
│   ├── service-classifier.ts     # ServiceSafety
│   └── types.ts                  # CommandType, PermissionResult
│
├── context/
│   ├── system-prompt.ts          # buildSystemPrompt()
│   ├── compact.ts                # compact 逻辑
│   └── truncation.ts             # truncateOutput()
│
├── events/
│   └── publisher.ts              # AgentEventPublisher
│
└── ssh/
    └── connector.ts              # SSH 连接
```

---

## 八、MVP 实现步骤

**目标**：用户提需求 → Agent 调用 service_exec → 完成

**MVP 只实现**：
- `service_exec` + `ask_user_question`（2 个 Tool）
- Docker + K8s 为主（SQL/MongoDB 后期加）
- 简单权限（危险词判断）
- 无 Compact、无 Plan、无 SSH

**步骤**：
1. `types.ts` — Message, ToolCall, AgentEvent, ToolDefinition, PermissionResult
2. `executors/registry.ts` — executeService 路由
3. `executors/docker.ts` — Docker Executor
4. `executors/kubernetes.ts` — K8s Executor
5. `tools/service-exec.ts` — service_exec Tool
6. `tools/ask-user-question.ts` — ask_user_question Tool
7. `tools/registry.ts` — buildToolRegistry（注册 2 个 Tool）
8. `context/system-prompt.ts` — buildSystemPrompt
9. `context/truncation.ts` — truncateOutput
10. `events/publisher.ts` — AgentEventPublisher（8 个核心事件）
11. `agent-loop.ts` — runAgent 主循环
12. `resume.ts` — resumeAgent
13. `index.ts` — 公共 API
14. DB schema — agent_sessions 表
15. API 路由 — run + resume SSE 端点

**后续补充**：

### Phase 1: 上下文自动注入 + SQL/MongoDB Executors

**目标**：Agent 启动即知道可用资源，并扩展数据库操作能力

**1. System Prompt 自动注入 servers/services 列表**
不做成独立 Tool，而是在 `getSystemPrompt(session)` 中自动查 DB 注入。
参考 Claude Code 的 attachment 模式：Agent 第一轮就能看到所有可用资源。

```typescript
// context/system-prompt.ts 中增加
async function getAvailableResources(): Promise<string> {
  const allServers = await db.select().from(servers);
  const allServices = await db.select().from(services);
  return [
    "## 可用资源",
    "",
    "### Servers (SSH)",
    allServers.map(s => `- ${s.name} (${s.host}:${s.port}) [ID: ${s.id}]`).join("\n"),
    "",
    "### Services",
    allServices.map(s => `- ${s.name} (${s.serviceType}, ${s.host}:${s.port}) [ID: ${s.id}]`).join("\n"),
  ].join("\n");
}
```

这样 system prompt 变成：BASE_PROMPT + 可用资源 + 计划 + compact 摘要

**2. SQL Executor（bun:sql）**
- `executors/sql.ts` — MySQL + PostgreSQL 共用
- 操作：executeSql, listTables, describeTable, listDatabases
- 连接用 `bun:sql`（Bun 内置）

**3. MongoDB Executor**
- `executors/mongodb.ts` — mongodb 官方驱动
- 操作：findDocuments, countDocuments, listCollections, aggregate, insertOne, updateMany, deleteMany

**4. messages 行表 role 修复**
修复 session.ts 中双写时 role 全写死 "system" 的问题，按事件类型区分。

**5. 从 Tool 清单中移除 list_servers/list_services**
这两个不再是独立 Tool，改为 system prompt 自动注入。

**实现步骤**：
1. `context/system-prompt.ts` — 改为 async，增加 DB 查询注入 servers/services
2. `agent-loop.ts` — 适配 async getSystemPrompt
3. `executors/sql.ts` — bun:sql executor
4. `executors/mongodb.ts` — mongodb executor
5. `executors/registry.ts` — 注册 mysql, postgresql, mongodb
6. `session.ts` — 修复 messages.role 按事件类型区分
7. 更新 E2E 测试

### Phase 2: `update_plan` + `search_knowledge`(混合检索) + `search_incidents`

**目标**：Agent 能制定/更新计划、混合检索知识库文档、搜索历史类似事件

**现有基础设施**：
- `lib/embedder.ts` — embedTexts()，DashScope text-embedding-v4，1024 维
- `lib/rerank.ts` — rerank()，qwen3-rerank 重排序
- `db/schema.ts` — documentChunks(embedding vector 1024)，incidentHistory(embedding vector 1024)
- `service/document.ts` — indexDocument() 已实现文档分块 + embedding 存储
- `agent-loop.ts` — 已有 `update_plan` 特殊处理
- `types.ts` — 已定义 `plan_updated` 事件

**检索策略（参考 Dify 混合检索设计）**：

```
用户查询
    │
    ├──────────────────────────┐
    ▼                          ▼
向量检索                    全文检索
(embedding <=> query)    (tsvector @@ tsquery)
    │                          │
    └───────────┬──────────────┘
                ▼
         去重 + 加权融合
     (vector_weight=0.7, text_weight=0.3)
                │
                ▼
         rerank 重排序
       (qwen3-rerank top 5)
                │
                ▼
            返回结果
```

#### 需要实现

**1. DB Schema 变更**

document_chunks 表加 tsvector 列 + GIN 索引：
```sql
ALTER TABLE document_chunks ADD COLUMN tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
CREATE INDEX ix_document_chunks_tsv ON document_chunks USING GIN(tsv);
```

incidentHistory 表加 tsvector 列 + GIN 索引：
```sql
ALTER TABLE incident_history ADD COLUMN tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', title || ' ' || summary_md)) STORED;
CREATE INDEX ix_incident_history_tsv ON incident_history USING GIN(tsv);
```

注意：用 `'simple'` 配置（不做词干提取），对中文友好。

**2. 混合检索函数（`lib/hybrid-search.ts`）**

```typescript
interface SearchResult {
  id: string;
  content: string;
  score: number;
  source: "vector" | "fulltext" | "both";
  metadata: Record<string, unknown>;
}

interface HybridSearchOptions {
  query: string;
  table: "document_chunks" | "incident_history";
  limit?: number;           // 默认 20（融合前的候选数）
  finalTopK?: number;       // 默认 5（rerank 后返回数）
  vectorWeight?: number;    // 默认 0.7
  textWeight?: number;      // 默认 0.3
  projectId?: string;       // 仅 document_chunks
  useRerank?: boolean;      // 默认 true
}

async function hybridSearch(options: HybridSearchOptions): Promise<SearchResult[]>
```

实现流程：
1. 并行执行：
   - 向量搜索：embedTexts([query]) → `SELECT *, 1-(embedding <=> $1) as score ... LIMIT limit`
   - 全文搜索：`SELECT *, ts_rank(tsv, plainto_tsquery('simple', $1)) as score ... LIMIT limit`
2. 去重（按 id），保留最高分
3. 加权融合：`final_score = vector_weight * v_score + text_weight * t_score`
4. rerank 重排序（可选）
5. 返回 top finalTopK 条

**3. update_plan Tool（`tools/update-plan.ts`）**

```typescript
schema: z.object({
  planMd: z.string().describe("Markdown 格式的调查计划"),
  intent: z.enum(["incident", "question", "task"]).optional(),
})
```

**4. search_knowledge Tool（`tools/search-knowledge.ts`）**

```typescript
schema: z.object({
  query: z.string().describe("搜索关键词或问题描述"),
  projectId: z.string().optional().describe("限定项目 ID"),
})
```

执行：hybridSearch(table: "document_chunks") → 返回结果含项目名、文档名、内容片段、相关度

**5. search_incidents Tool（`tools/search-incidents.ts`）**

```typescript
schema: z.object({
  query: z.string().describe("搜索关键词或问题描述"),
})
```

执行：hybridSearch(table: "incident_history") → 返回历史事件标题、摘要、发生次数

**6. System Prompt 增强**

工具使用原则追加：
```
- search_knowledge: 排查前先搜索项目知识库，了解系统架构、配置和常见问题
- search_incidents: 搜索历史类似事件，参考之前的排查经验和解决方案
- update_plan: 收集信息后制定调查计划，排查过程中发现新线索时更新计划
```

**实现步骤**：
1. `db/schema.ts` — documentChunks 加 tsv 列，incidentHistory 加 tsv 列
2. `db:push` — 推送 schema 变更
3. `lib/hybrid-search.ts` — 混合检索函数（向量+全文+融合+rerank）
4. `tools/update-plan.ts`
5. `tools/search-knowledge.ts`
6. `tools/search-incidents.ts`
7. `tools/registry.ts` — 注册 3 个新 Tool（总共 5 个）
8. `context/system-prompt.ts` — 增强工具说明
9. E2E 测试

**E2E 测试（2 个场景）**：

**场景 1：知识库混合检索 + Docker 排查**
```
测试文件：tests/ops-agent/agent-search.test.ts

准备：
  1. 创建项目 "test-project"
  2. 创建文档，内容为 nginx 运维知识：
     "nginx 返回 502 通常是后端服务不可用。排查步骤：
      1. 检查 upstream 服务是否存活
      2. 查看 nginx error.log
      3. 检查端口是否被占用"
  3. 调用 indexDocument() 索引文档（生成 embedding + chunks）
  4. 创建 Docker service + 启动 nginx 容器
  5. 创建 incident

提问："nginx 返回 502 错误，请帮我排查"

期望 Agent 行为：
  Turn 1-2: search_knowledge("nginx 502") → 找到文档 → 拿到排查步骤
  Turn 2-3: service_exec(docker, listContainers) → 检查容器状态
  Turn N: 输出总结（引用知识库内容 + 实际检查结果）

验证：
  - SSE 包含 search_knowledge 的 tool_start + tool_result
  - tool_result 中包含 "upstream" 或 "502" 关键词
  - 最终 done 事件存在
  - DB session.status = "completed"
```

**场景 2：制定计划 + 历史事件搜索 + 排查**
```
准备：
  1. 在 incident_history 表插入一条历史事件：
     title: "nginx OOM 导致服务中断"
     summaryMd: "容器内存不足触发 OOM Killer..."
     embedding: embedTexts(["nginx OOM 导致服务中断"])[0]
  2. 创建 Docker service + 启动 nginx 容器
  3. 创建 incident

提问："nginx 容器疑似内存异常，请系统性排查"

期望 Agent 行为：
  Turn 1: search_incidents("nginx 内存异常") → 找到历史 OOM 事件
  Turn 2: update_plan → 制定计划（参考历史经验）
  Turn 3+: service_exec 按计划排查
  Turn N: 输出总结

验证：
  - SSE 包含 search_incidents 的 tool_result（含 "OOM"）
  - SSE 包含 plan_updated 事件
  - DB session.planMd 有值
  - DB session.status = "completed"
```
### Phase 3: 完整 Safety Classifier + `ssh_bash` + `bash`
### Phase 4: Compact 机制

### 后续阶段实现时的设计注意点

**1. incidents.summaryTitle 同步**
Agent 完成时（`session.status = "completed"`），需要同步更新 `incidents.summaryTitle`。
可以用 LLM 从 `session.summary` 生成一个短标题，或者直接截取前 100 字。
在 `saveSession` 的 done 分支或 Agent 完成后的 post-processing 中处理。

**2. messages 行表的 role 字段语义**
当前双写时 role 全写死了 `"system"`，后续应按事件类型区分：
- `thinking`、`ask_user_question` → `"assistant"`（Agent 产出）
- 用户回复 → `"user"`
- `tool_start`、`tool_result`、`approval_required`、`done`、`error` → `"system"`

**3. pendingApprovalId 无外键约束**
`agent_sessions.pendingApprovalId` 故意没加外键到 `approval_requests`，避免循环依赖。
一致性由应用层保证：创建 approval 和设置 pendingApprovalId 在同一个 saveSession 事务中完成。

**4. Agent 完成后的 incident 状态同步**
`agent_sessions.status` 和 `incidents.status` 是独立的两个状态：
- `agent_sessions.status` = Agent 执行状态（running/interrupted/completed/failed）
- `incidents.status` = 业务状态（open/resolved/closed）
Agent 完成不等于 incident 解决。Agent done 后 incident 仍然是 open，
需要用户在前端手动确认"已解决"才改为 resolved。
或者通过 `confirm` 类型的 resume 来触发。

**5. agentMessages JSONB 体积控制**
随着排查轮次增加，agentMessages 可能膨胀到几百 KB 甚至 MB 级别。
Phase 4 实现 Compact 时需要注意：
- compact 后替换 agentMessages 为压缩版本，旧的完整历史可存入 `content_versions` 表做归档
- PostgreSQL JSONB 单字段建议不超过几 MB，超过需要考虑拆分或归档策略

**6. service_exec 的 operation 命名规范**
各 Executor 的 operation 名称需要保持一致的命名风格（camelCase），
并且在 System Prompt 或 Tool description 中明确列出每种 service type 支持的 operation 清单，
避免 LLM 编造不存在的 operation 名称。

---

## 九、验证

### 9.1 日志要求

在 agent-loop.ts 和相关模块的每个关键节点加入醒目日志（大写前缀），用 pino logger：

```
[AGENT] ========== TURN 1 START ==========
[AGENT] SYSTEM PROMPT: (前200字)
[AGENT] CALLING LLM: model=qwen3.6-plus, messages=3
[AGENT] LLM RESPONSE: text="..." toolCalls=2
[AGENT] TOOL CALL: name=service_exec, args={serviceId: "xxx", operation: "listContainers"}
[AGENT] PERMISSION CHECK: service_exec → allow (read operation)
[AGENT] TOOL EXECUTING: service_exec...
[AGENT] TOOL RESULT: service_exec → 1523 chars
[AGENT] TOOL CALL: name=ask_user_question, args={question: "需要重启吗？"}
[AGENT] INTERRUPTED: ask_user_question, saving session...
[AGENT] SESSION SAVED: turn=1, status=interrupted, messages=5
```

需要日志的关键节点：
1. **每轮循环开始** — turn 编号
2. **LLM 调用前** — 模型名、消息数量
3. **LLM 返回后** — 文本摘要、toolCalls 数量和名称
4. **每个 tool call** — 工具名、参数摘要
5. **权限检查结果** — allow/ask/deny + 原因
6. **工具执行前后** — 开始执行、结果长度或错误
7. **中断事件** — 中断类型、保存状态
8. **Session 持久化** — turn 数、status、messages 数量
9. **Agent 完成/失败** — 最终状态、总轮次

### 9.2 端到端测试用例

**文件**: `server/tests/ops-agent/agent-e2e.test.ts`

**测试环境准备**（在 test setup 中）：
1. 本地 Docker 已开启（macOS OrbStack，socket: `/var/run/docker.sock`）
2. 创建测试用 incident 和 service 记录
3. Service 配置使用 Docker socket 连接（不走 TCP）

```typescript
// 测试用例伪代码

describe("Ops Agent E2E", () => {
  let token: string;
  let incidentId: string;
  let dockerServiceId: string;

  beforeEach(async () => {
    // 1. 注册登录
    token = await registerAndLogin();

    // 2. 创建 Docker service（本地 socket 连接）
    const svcRes = await request("POST", "/api/services", {
      token,
      body: {
        name: "local-docker",
        serviceType: "docker",
        host: "localhost",
        port: 2376,
        config: { socketPath: "/var/run/docker.sock" },
      },
    });
    dockerServiceId = (await json(svcRes)).id;

    // 3. 启动一个测试容器（nginx）
    // docker run -d --name chronos-test-nginx -p 18080:80 nginx:alpine
    const docker = new Docker({ socketPath: "/var/run/docker.sock" });
    await docker.pull("nginx:alpine");
    const container = await docker.createContainer({
      Image: "nginx:alpine",
      name: "chronos-test-nginx",
      HostConfig: { PortBindings: { "80/tcp": [{ HostPort: "18080" }] } },
    });
    await container.start();

    // 4. 创建 incident
    const incRes = await request("POST", "/rpc/incident.create", {
      token,
      body: { description: "测试: nginx 容器状态检查", severity: "P3" },
    });
    incidentId = (await json(incRes)).id;
  });

  afterEach(async () => {
    // 清理测试容器
    const docker = new Docker({ socketPath: "/var/run/docker.sock" });
    try {
      const c = docker.getContainer("chronos-test-nginx");
      await c.stop();
      await c.remove();
    } catch {}
  });

  it("Agent 应能查询 Docker 容器并返回总结", async () => {
    // 触发 Agent
    const res = await request("POST", `/api/agent/${incidentId}/run`, {
      token,
      body: {
        prompt: `请检查 Docker 服务（service ID: ${dockerServiceId}）中的容器运行状态，
                 特别关注名为 chronos-test-nginx 的容器是否正常运行。`,
      },
    });

    expect(res.status).toBe(200);

    // 读取 SSE 事件流
    const text = await res.text();
    const events = parseSSEEvents(text);

    // 验证事件流包含关键事件
    expect(events.some(e => e.type === "session_started")).toBe(true);
    expect(events.some(e => e.type === "tool_start" && e.data.toolName === "service_exec")).toBe(true);
    expect(events.some(e => e.type === "tool_result" && e.data.output.includes("chronos-test-nginx"))).toBe(true);
    expect(events.some(e => e.type === "done")).toBe(true);

    // 验证 DB 状态
    const session = await loadSession(incidentId);
    expect(session.status).toBe("completed");
    expect(session.summary).toContain("nginx");
    expect(session.turnCount).toBeGreaterThan(0);
  });
});

// SSE 解析辅助函数
function parseSSEEvents(raw: string) {
  return raw
    .split("\n\n")
    .filter(block => block.includes("event:"))
    .map(block => {
      const eventMatch = block.match(/event:\s*(.+)/);
      const dataMatch = block.match(/data:\s*(.+)/);
      return {
        type: eventMatch?.[1] || "",
        data: dataMatch?.[1] ? JSON.parse(dataMatch[1]) : {},
      };
    });
}
```

**注意**：`tests/setup.ts` 的 TRUNCATE 语句需要加入 `agent_sessions` 表。

**这个测试验证的完整链路**：
```
创建 incident + docker service + 启动 nginx 容器
    ↓
POST /api/agent/:id/run { prompt: "检查容器状态" }
    ↓
Agent while 循环:
  Turn 1: LLM → 决定调用 service_exec(docker, listContainers)
  Turn 2: LLM 看到容器列表 → 可能调用 inspectContainer
  Turn N: LLM 输出总结 → 无 toolCalls → done
    ↓
验证: SSE 事件流包含 session_started → tool_start → tool_result → done
验证: DB 中 session.status=completed, summary 包含 nginx
```
