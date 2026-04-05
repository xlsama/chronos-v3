# Chronos V3 Ops AI Agent 设计方案

## Context


本方案参考 Claude Code 的核心设计：**单 `while` 循环 + messages 数组驱动**。不用任何框架，不用显式状态枚举，状态全部保存在 messages 中。

---

## 一、核心架构：单 while 循环 + Messages 驱动

### 1.1 设计原则

直接从 Claude Code `queryLoop()` 源码提炼的核心模式：

1. **整个 Agent 就是一个 `while(true)` 循环**
2. **状态 = messages 数组**，所有上下文、工具结果、用户回复都是 messages
3. **LLM 决定一切**：调什么工具、什么时候结束、什么时候问用户 — 都是模型自己通过 tool_calls 决定的
4. **循环只做三件事**：调 LLM → 执行工具 → 把结果追加到 messages → 继续
5. **没有工具调用 = 任务完成**（和 Claude Code 一样）

### 1.2 Claude Code queryLoop 流转图（供参考）

```
用户发送消息
    │
    ▼
┌══════════════════════════════════════════════════════════════┐
║ queryLoop() —— while(true)                                  ║
║                                                              ║
║  ① 压缩预处理（snip → micro → collapse → autoCompact）       ║
║                         │                                    ║
║  ② 调用 LLM API（流式） │                                    ║
║     → 收集 assistantMessage + toolUseBlocks                  ║
║                         │                                    ║
║  ③ 没有 toolCalls?                                           ║
║     YES → return { reason: 'completed' }  // 结束            ║
║     NO  ↓                                                    ║
║                                                              ║
║  ④ 执行工具 runTools()                                       ║
║     → partitionToolCalls: 只读并发，写操作串行                 ║
║     → 每个工具: 权限检查 → 执行 → yield 结果                  ║
║                         │                                    ║
║  ⑤ messages = [...messages, assistant, ...toolResults]       ║
║     → continue 回到 ①                                        ║
╚══════════════════════════════════════════════════════════════╝
```

### 1.3 我们的 runAgent 流转图

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
║     ┌─ ServiceExec → 权限检查 → 执行/审批中断                │
║     ├─ SSHBash     → 权限检查 → 执行/审批中断                │
║     ├─ bash         → 权限检查 → 执行/审批中断                │
║     ├─ AskUserQuestion     → yield 问题, interrupt                  │
║     ├─ UpdatePlan   → 创建/更新调查计划                       │
║     └─ 其他只读工具  → 直接执行                                │
║                         │                                    ║
║     如果需要审批:                                             ║
║       → 存 messages 到 DB                                    ║
║       → status = 'interrupted'                               ║
║       → return（等待 resume）                                 ║
║                         │                                    ║
║  ⑤ 工具结果追加到 messages                                    ║
║     → 持久化到 DB                                             ║
║     → continue 回到 ①                                        ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 二、数据结构

### 2.1 Session（存 DB，incidents 表扩展）

```typescript
// DB 中 incidents 表的扩展字段
interface IncidentAgent {
  status: "running" | "interrupted" | "completed";
  messages: Message[];          // 完整对话历史 = 全部状态
  turnCount: number;
  maxTurns: number;             // 默认 30，防死循环
  compactMd: string | null;     // compact 摘要
  planMd: string | null;        // 当前计划（plan mode 产出）
}
```

### 2.2 Message

```typescript
type Message =
  | { role: "system"; content: string }
  | { role: "user"; content: string | ContentPart[] }
  | { role: "assistant"; content: string; toolCalls?: ToolCall[] }
  | { role: "tool"; toolCallId: string; content: string };

interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}
```

---

## 三、runAgent 核心实现

```typescript
async function* runAgent(
  incidentId: string,
  initialPrompt?: string,
): AsyncGenerator<AgentEvent> {
  // 加载或创建 session
  let session = await loadSession(incidentId);
  if (initialPrompt) {
    session.messages.push({ role: "user", content: initialPrompt });
  }

  const tools = buildToolRegistry();

  while (true) {
    // 1. 防死循环
    session.turnCount++;
    if (session.turnCount > session.maxTurns) {
      yield { type: "error", message: "达到最大循环次数，任务终止" };
      session.status = "completed";
      break;
    }

    // 2. compact 检查
    if (shouldCompact(session.messages)) {
      const compactMd = await compactMessages(session);
      session.compactMd = compactMd;
      session.messages = rebuildMessagesAfterCompact(session);
      yield { type: "compact_done", compactMd };
    }

    // 3. 调用 LLM
    const llmResult = yield* callLLM({
      system: buildSystemPrompt(session),
      messages: session.messages,
      tools: tools.map(t => t.definition),
    });

    // 4. 记录 assistant 回复
    session.messages.push(llmResult.assistantMessage);

    // 5. 没有 tool call → 任务完成
    if (!llmResult.toolCalls || llmResult.toolCalls.length === 0) {
      session.status = "completed";
      yield { type: "done" };
      break;
    }

    // 6. 执行工具
    for (const tc of llmResult.toolCalls) {
      const tool = tools.find(t => t.name === tc.name);
      if (!tool) {
        session.messages.push({
          role: "tool", toolCallId: tc.id,
          content: `未知工具: ${tc.name}`,
        });
        continue;
      }

      // 权限检查（仅 ServiceExec, SSHBash, bash）
      if (tool.needsPermissionCheck) {
        const perm = await tool.checkPermission(tc.args);

        if (perm.behavior === "deny") {
          session.messages.push({
            role: "tool", toolCallId: tc.id,
            content: `操作被拒绝: ${perm.reason}`,
          });
          yield { type: "tool_denied", name: tc.name, reason: perm.reason };
          continue;
        }

        if (perm.behavior === "ask") {
          // 创建审批请求，中断等审批
          const approvalId = await createApproval(incidentId, tc, perm);
          yield {
            type: "approval_required",
            approvalId,
            toolName: tc.name,
            toolArgs: tc.args,
            riskLevel: perm.riskLevel,
          };
          // 保存状态，中断
          session.status = "interrupted";
          await saveSession(incidentId, session);
          return; // 等待 resume
        }
      }

      // 执行工具
      yield { type: "tool_start", name: tc.name, args: tc.args };
      try {
        const result = await tool.execute(tc.args);
        const output = truncateOutput(String(result), tool.maxResultChars);
        session.messages.push({ role: "tool", toolCallId: tc.id, content: output });
        yield { type: "tool_result", name: tc.name, output };
      } catch (err) {
        const errMsg = `执行失败: ${err.message}`;
        session.messages.push({ role: "tool", toolCallId: tc.id, content: errMsg });
        yield { type: "tool_error", name: tc.name, error: errMsg };
      }
    }

    // 7. 每轮持久化
    await saveSession(incidentId, session);
  }

  // 最终持久化
  await saveSession(incidentId, session);
}
```

### 3.1 Resume（恢复）

```typescript
async function* resumeAgent(
  incidentId: string,
  input: ResumeInput,
): AsyncGenerator<AgentEvent> {
  const session = await loadSession(incidentId);

  switch (input.type) {
    case "approval":
      if (input.decision === "approved") {
        // 执行被暂停的工具
        const pendingTc = session.pendingToolCall!;
        const tool = getToolByName(pendingTc.name);
        const result = await tool.execute(pendingTc.args);
        session.messages.push({
          role: "tool", toolCallId: pendingTc.id,
          content: truncateOutput(String(result), tool.maxResultChars),
        });
      } else {
        session.messages.push({
          role: "tool", toolCallId: session.pendingToolCall!.id,
          content: `操作被用户拒绝: ${input.feedback || ""}`,
        });
      }
      break;

    case "human_input":
      session.messages.push({ role: "user", content: input.text });
      break;

    case "confirm":
      if (input.confirmed) {
        session.status = "completed";
        yield { type: "done" };
        await saveSession(incidentId, session);
        return;
      }
      session.messages.push({
        role: "user",
        content: `[用户反馈] 问题未解决: ${input.text || ""}`,
      });
      break;
  }

  session.status = "running";
  session.pendingToolCall = null;

  // 继续主循环
  yield* runAgent(incidentId);
}
```

---

## 四、Tool 系统

### 4.1 Tool 定义接口

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

### 4.2 Tool 清单

| Tool | 说明 | 权限检查 |
|------|------|---------|
| `ServiceExec` | 核心 Tool，执行所有 Service 操作 | ServiceSafety 分类 |
| `SSHBash` | SSH 到远程服务器执行命令 | ShellSafety 分类 |
| `Bash` | 本地执行命令 | ShellSafety 分类(local) |
| `AskUserQuestion` | 向用户提问，中断等回复 | 无 |
| `SearchKnowledge` | 向量搜索项目知识库 | 无 |
| `SearchIncidents` | 搜索历史类似事件 | 无 |
| `ListServers` | 列出可用服务器 | 无 |
| `ListServices` | 列出可用服务连接 | 无 |
| `UpdatePlan` | 创建/更新调查计划，存入 DB | 无 |

### 4.3 ServiceExec — 核心 Tool

一个"超级 Tool"，通过 `serviceId` + `operation` + `parameters` 路由到不同的 Executor。

```typescript
const ServiceExecTool: ToolDefinition = {
  name: "ServiceExec",
  description: `执行预注册的 Service 操作（Docker/K8s/MySQL/PostgreSQL/MongoDB）。
所有操作通过结构化参数执行，禁止输出 shell 命令字符串。`,
  parameters: z.object({
    serviceId: z.string().describe("Service ID"),
    operation: z.string().describe("操作名: listContainers, executeSql, findDocuments 等"),
    parameters: z.record(z.any()).optional().describe("操作参数"),
  }),
  needsPermissionCheck: true,
  maxResultChars: 30_000,

  async checkPermission(args) {
    const service = await getService(args.serviceId);
    const cmdType = ServiceSafety.classify(service.type, args.operation, args.parameters);
    return commandTypeToPermission(cmdType);
  },

  async execute(args) {
    return executeService(args.serviceId, args.operation, args.parameters);
  },
};
```

### 4.4 Executor Registry

```typescript
// service/executor-registry.ts
const executors: Record<string, Executor> = {
  docker: dockerExecutor,      // dockerode
  kubernetes: k8sExecutor,     // @kubernetes/client-node
  mysql: sqlExecutor,          // bun:sql
  postgresql: sqlExecutor,     // bun:sql
  mongodb: mongoExecutor,      // mongodb 官方驱动
};

async function executeService(serviceId: string, operation: string, params: any) {
  const service = await db.services.findById(serviceId);
  const executor = executors[service.type];
  if (!executor) throw new Error(`不支持的 Service Type: ${service.type}`);
  return executor(service.connectionInfo, operation, params);
}
```

### 4.5 各 Executor 示例

**Docker**（dockerode）：
```typescript
async function dockerExecutor(conn, operation, params) {
  const docker = new Docker({ host: conn.host, port: conn.port, ... });
  const handlers = {
    listContainers: () => docker.listContainers(params || { all: true }),
    startContainer: () => docker.getContainer(params.containerId).start(),
    stopContainer: () => docker.getContainer(params.containerId).stop(),
    restartContainer: () => docker.getContainer(params.containerId).restart(),
    removeContainer: () => docker.getContainer(params.containerId).remove(),
    inspectContainer: () => docker.getContainer(params.containerId).inspect(),
    containerLogs: () => docker.getContainer(params.containerId).logs({ tail: params.tail || 100, stdout: true, stderr: true }),
    listImages: () => docker.listImages(),
    // ...
  };
  const handler = handlers[operation];
  if (!handler) throw new Error(`Docker 不支持操作: ${operation}`);
  return handler();
}
```

**K8s**（@kubernetes/client-node）：
```typescript
async function k8sExecutor(conn, operation, params) {
  const kc = new k8s.KubeConfig();
  kc.loadFromString(conn.kubeconfig);
  const core = kc.makeApiClient(k8s.CoreV1Api);
  const apps = kc.makeApiClient(k8s.AppsV1Api);
  const handlers = {
    listPods: () => core.listNamespacedPod(params.namespace || "default"),
    describePod: () => core.readNamespacedPod(params.name, params.namespace),
    getPodLogs: () => core.readNamespacedPodLog(params.name, params.namespace, { tailLines: params.tail || 100 }),
    listDeployments: () => apps.listNamespacedDeployment(params.namespace || "default"),
    scaleDeployment: () => apps.patchNamespacedDeploymentScale(params.name, params.namespace, { spec: { replicas: params.replicas } }),
    deletePod: () => core.deleteNamespacedPod(params.name, params.namespace),
    // ...
  };
  const handler = handlers[operation];
  if (!handler) throw new Error(`K8s 不支持操作: ${operation}`);
  return handler();
}
```

**SQL**（bun:sql，MySQL/PostgreSQL 共用）：
```typescript
async function sqlExecutor(conn, operation, params) {
  const sql = new SQL({ host: conn.host, port: conn.port, user: conn.username, password: conn.password, database: conn.database });
  const handlers = {
    executeSql: async () => {
      const result = await sql.unsafe(params.query);
      return result;
    },
    listTables: () => sql.unsafe("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"),
    describeTable: () => sql.unsafe(`SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '${params.table}'`),
  };
  const handler = handlers[operation];
  if (!handler) throw new Error(`SQL 不支持操作: ${operation}`);
  const result = await handler();
  await sql.close();
  return result;
}
```

**MongoDB**（官方驱动）：
```typescript
async function mongoExecutor(conn, operation, params) {
  const client = new MongoClient(conn.uri);
  await client.connect();
  const db = client.db(params.database || conn.defaultDb);
  const handlers = {
    listCollections: () => db.listCollections().toArray(),
    findDocuments: () => db.collection(params.collection).find(params.filter || {}).limit(params.limit || 100).toArray(),
    countDocuments: () => db.collection(params.collection).countDocuments(params.filter || {}),
    insertOne: () => db.collection(params.collection).insertOne(params.document),
    updateMany: () => db.collection(params.collection).updateMany(params.filter, params.update),
    deleteMany: () => db.collection(params.collection).deleteMany(params.filter),
    aggregate: () => db.collection(params.collection).aggregate(params.pipeline).toArray(),
    // ...
  };
  const handler = handlers[operation];
  if (!handler) throw new Error(`MongoDB 不支持操作: ${operation}`);
  const result = await handler();
  await client.close();
  return result;
}
```

---

## 五、UpdatePlan 工具

### 5.1 工作原理

不是模式切换，而是一个普通的协调工具。Agent 在主循环中自然地先收集信息、制定计划，然后调用 `UpdatePlan` 把计划落盘。排查过程中发现新线索时也可以再次调用来更新计划。

典型流程：
```
while(true) {
  LLM: "先看看有哪些资源"
    → ListServers, ListServices, SearchKnowledge

  LLM: "制定调查计划"
    → UpdatePlan({ planMd: "H1: ... H2: ...", intent: "incident" })

  LLM: "开始执行 H1"
    → ServiceExec(docker, listContainers)
    → ...

  LLM: "H1 排除，发现新线索，更新计划"
    → UpdatePlan({ planMd: "H1: 已排除 ..." })
}
```

### 5.2 实现

```typescript
const UpdatePlanTool: ToolDefinition = {
  name: "UpdatePlan",
  description: "创建或更新调查计划。首次调用为创建，后续调用为更新。计划会持久化到数据库。",
  parameters: z.object({
    planMd: z.string().describe("Markdown 格式的调查计划"),
    intent: z.enum(["incident", "question", "task"]).optional()
      .describe("事件意图分类（首次创建时必填）"),
  }),
  needsPermissionCheck: false,
  maxResultChars: 1000,
  async execute(args) {
    // 主循环会把 planMd 存入 session.planMd
    return "计划已更新。";
  },
};
```

### 5.3 System Prompt 中的计划指导

System Prompt 中引导 Agent 先 plan 后 execute：
```
你是一个运维排查助手。收到事件后，请遵循以下流程：
1. 先用 ListServers/ListServices/SearchKnowledge 等工具收集信息
2. 信息不足时用 AskUserQuestion 向用户补充
3. 信息充足后调用 UpdatePlan 制定调查计划
4. 按计划逐步用 ServiceExec 等工具排查
5. 排查过程中发现新线索，再次调用 UpdatePlan 更新计划
6. 完成后输出总结（不调用任何工具即视为完成）
```

---

## 六、权限分类器

### 6.1 统一接口

```typescript
type CommandType = "read" | "write" | "dangerous" | "blocked";

interface PermissionResult {
  behavior: "allow" | "ask" | "deny";
  reason: string;
  riskLevel: "MEDIUM" | "HIGH" | "";
}

function commandTypeToPermission(type: CommandType): PermissionResult {
  switch (type) {
    case "read":      return { behavior: "allow", reason: "", riskLevel: "" };
    case "write":     return { behavior: "ask", reason: "写操作需要审批", riskLevel: "MEDIUM" };
    case "dangerous": return { behavior: "ask", reason: "高风险操作", riskLevel: "HIGH" };
    case "blocked":   return { behavior: "deny", reason: "操作被禁止", riskLevel: "" };
  }
}
```

### 6.2 ShellSafety（SSHBash / bash 权限）

直接移植 Python 版 `shell_classifier.py` 的正则分类：

```
BLOCKED: rm -rf /, fork bomb, 写入块设备, .env 访问(本地)
DANGEROUS: rm -rf, kill -9, DROP TABLE, kubectl delete, docker rm, systemctl restart
WRITE: sed -i, curl -X POST, wget, 输出重定向, 命令替换 $()
READ: 白名单前缀 (ls, cat, ps, docker ps, kubectl get, ...)
默认: WRITE（fail-closed）
```

### 6.3 ServiceSafety（ServiceExec 权限）

针对 `ServiceExec` 的 `operation` 做分类：

```typescript
const SERVICE_CLASSIFIERS: Record<string, (op: string, params: any) => CommandType> = {
  docker: classifyDocker,       // listContainers=read, restart=write, rm=dangerous
  kubernetes: classifyK8s,      // listPods=read, scale=write, delete=dangerous
  mysql: classifySql,           // executeSql 内部解析 SQL 语句
  postgresql: classifySql,
  mongodb: classifyMongo,       // findDocuments=read, insertOne=write, drop=dangerous
};
```

---

## 七、Compact 机制

### 7.1 触发条件

```typescript
function shouldCompact(messages: Message[]): boolean {
  const totalChars = messages.reduce((sum, m) => {
    const content = typeof m.content === "string" ? m.content : JSON.stringify(m.content);
    return sum + content.length;
  }, 0);
  return totalChars > COMPACT_THRESHOLD; // 默认 80000 字符
}
```

### 7.2 压缩流程

1. 用 mini_model 生成结构化摘要（保留计划、结论、关键证据）
2. 替换 messages 为：`[system摘要, 当前计划, 最近 N 条消息]`
3. 存入 `session.compactMd`

---

## 八、事件流（SSE）

```typescript
type AgentEvent =
  | { type: "thinking"; content: string }
  | { type: "answer"; content: string }
  | { type: "tool_start"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; output: string }
  | { type: "tool_denied"; name: string; reason: string }
  | { type: "tool_error"; name: string; error: string }
  | { type: "approval_required"; approvalId: string; toolName: string; toolArgs: Record<string, unknown>; riskLevel: string }
  | { type: "AskUserQuestion"; question: string }
  | { type: "plan_generated"; planMd: string }
  | { type: "compact_done"; compactMd: string }
  | { type: "done" }
  | { type: "error"; message: string };
```

### API 端点

```typescript
POST /api/incidents/:id/run    → SSE stream (runAgent)
POST /api/incidents/:id/resume → SSE stream (resumeAgent)
```

---

## 九、目录结构

```
server/src/ops-agent/
├── index.ts                    # 公共 API: runAgent, resumeAgent
├── types.ts                    # Message, ToolCall, AgentEvent, PermissionResult
├── agent-loop.ts               # runAgent 主循环
├── resume.ts                   # resumeAgent 恢复逻辑
│
├── tools/
│   ├── registry.ts             # buildToolRegistry(), ToolDefinition 接口
│   ├── ServiceExecTool.ts      # ServiceExecTool (核心)
│   ├── SSHBashTool.ts          # SSHBashTool
│   ├── BashTool.ts             # BashTool (本地)
│   ├── AskUserQuestionTool.ts  # AskUserQuestionTool
│   ├── UpdatePlanTool.ts      # UpdatePlanTool
│   ├── SearchKnowledgeTool.ts  # SearchKnowledgeTool
│   ├── SearchIncidentsTool.ts  # SearchIncidentsTool
│   ├── ListServersTool.ts      # ListServersTool
│   └── ListServicesTool.ts     # ListServicesTool
│
├── executors/
│   ├── registry.ts             # executeService(), Executor 注册
│   ├── docker.ts               # dockerode
│   ├── kubernetes.ts           # @kubernetes/client-node
│   ├── sql.ts                  # bun:sql (MySQL + PostgreSQL)
│   └── mongodb.ts              # mongodb 官方驱动
│
├── safety/
│   ├── shell-classifier.ts     # ShellSafety (正则分类)
│   ├── service-classifier.ts   # ServiceSafety (按 service type)
│   └── types.ts                # CommandType, PermissionResult
│
├── context/
│   ├── compact.ts              # compact 逻辑
│   ├── compact-prompts.ts      # compact system prompt
│   ├── system-prompt.ts        # buildSystemPrompt()
│   └── truncation.ts           # truncateOutput()
│
├── events/
│   └── publisher.ts            # SSE 事件发布
│
└── ssh/
    └── connector.ts            # SSH 连接 (ssh2, bastion)
```

---

## 十、数据库设计

### 10.1 设计思路

**核心原则**：Agent 状态 = messages JSONB。新建 `agent_sessions` 表，和 `incidents` 一对一关联，职责分离。

**双写模式**：
- `agent_sessions.messages`（JSONB）= Agent 循环的 LLM 上下文，用于中断恢复
- `messages` 表（行级）= 前端 SSE 事件持久化，用于展示和审计

### 10.2 agent_sessions 表（Drizzle schema）

```typescript
export const agentSessions = pgTable(
  "agent_sessions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    incidentId: uuid("incident_id")
      .notNull()
      .references(() => incidents.id, { onDelete: "cascade" })
      .unique(), // 一个 incident 只有一个 agent session

    status: varchar("status", { length: 20 })
      .notNull()
      .default("running"),
    // running | interrupted | completed | failed

    // ═══ 核心状态 ═══
    agentMessages: jsonb("agent_messages").notNull().default([]),
    // Agent 循环的完整 LLM 消息历史（Message[]）
    // 这是 Agent 恢复的唯一数据源

    turnCount: integer("turn_count").notNull().default(0),
    maxTurns: integer("max_turns").notNull().default(30),

    // ═══ Plan ═══
    planMd: text("plan_md"),
    // Plan Mode 产出的计划，也注入到 system prompt

    // ═══ Compact ═══
    compactMd: text("compact_md"),
    // 最近一次 compact 的摘要

    // ═══ 中断恢复 ═══
    pendingToolCall: jsonb("pending_tool_call"),
    // 被审批暂停的 tool call: { id, name, args }

    pendingApprovalId: uuid("pending_approval_id"),
    // 关联 approval_requests 表

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

### 10.3 为什么用 JSONB 存 messages

| 考虑 | 结论 |
|------|------|
| 读写模式 | 每轮循环整体读写一次，JSONB 完美匹配 |
| 数据量 | 通常 100-500KB（compact 后更小），PostgreSQL JSONB 轻松处理 |
| 恢复需求 | 只需要整体加载，不需要按条件查单条 |
| 演进友好 | Message 结构变化不用改表 |
| 审计/搜索 | 用 `messages` 行表做，不靠这个 JSONB |

### 10.4 已有表的调整

**incidents 表**：
- `planMd` 保留（Agent 产出的计划也同步到这里，供前端展示）
- `status` 含义不变（open/resolved/closed），和 agent session 的 status 独立

**messages 表**：
- 继续用于 SSE 事件持久化（前端展示）
- Agent 循环中每个事件都往这里 INSERT 一行
- `event_type` 区分：`tool_call`, `tool_result`, `thinking`, `answer`, `approval_required`, `AskUserQuestion` 等

**approval_requests 表**：
- 已有，不需要改
- `agent_sessions.pendingApprovalId` 关联到这里

### 10.5 future-proof 考虑

| 未来场景 | 表设计如何支持 |
|---------|-------------|
| 多轮对话（用户多次追问） | 同一 session，messages 持续追加 |
| Sub-Agent | 在 agentMessages JSONB 内部区分（通过 message metadata），不需要新表 |
| 事件关联多个项目 | incidents 表加 projectIds 字段（已有知识库关联） |
| 历史事件学习 | 完成后从 agentMessages 提取关键步骤存入 incident_history |
| 计费/统计 | 从 messages 行表聚合 token 数 |
| Compact 历史 | compactMd 只存最新一次，历史 compact 可存 content_versions |

---

## 十一、实现顺序

### MVP（Phase 0）— 先跑通核心链路

**目标**：用户提需求 → Agent 调用 ServiceExec → 完成

**只保留 2 个 Tool**：
- `ServiceExec` — 核心
- `AskUserQuestion` — 信息不足时问用户

**简化项**：
- 权限检查：简单版，只判断 operation 是否包含危险词（delete/remove/drop/kill/restart）
- Compact：不做，或只做最简单的 messages 数量截断（超过 N 条删旧的）
- 不做：SSHBash, Bash, UpdatePlan, SearchKnowledge, SearchIncidents
- 不做：ShellSafety, ServiceSafety 完整正则分类器

**实现步骤**：
1. `types.ts` — Message, ToolCall, AgentEvent, ToolDefinition
2. `executors/registry.ts` — executeService 路由
3. `executors/docker.ts` — Docker Executor（dockerode）
4. `executors/kubernetes.ts` — K8s Executor（@kubernetes/client-node）
5. `executors/sql.ts` — SQL Executor（bun:sql，MySQL + PostgreSQL）
6. `executors/mongodb.ts` — MongoDB Executor（mongodb）
7. `tools/ServiceExecTool.ts` — ServiceExecTool（简单权限检查）
8. `tools/AskUserQuestionTool.ts` — AskUserQuestionTool
9. `tools/registry.ts` — buildToolRegistry（只注册上面 2 个）
10. `context/system-prompt.ts` — buildSystemPrompt（基础版）
11. `context/truncation.ts` — truncateOutput
12. `agent-loop.ts` — runAgent 主循环
13. `resume.ts` — resumeAgent
14. `events/publisher.ts` — SSE 事件
15. `index.ts` — 公共 API
16. DB schema 更新 + API 路由

### Phase 1: 补齐只读工具
- `list-servers.ts`, `list-services.ts`
- `search-knowledge.ts`, `search-incidents.ts`

### Phase 2: Plan Mode
- `enter-plan.ts`, `exit-plan.ts`
- System Prompt 动态注入 plan 指导

### Phase 3: 完整权限系统
- `safety/shell-classifier.ts` — 移植 Python 版正则分类器
- `safety/service-classifier.ts` — 按 service type 分类
- `ssh/connector.ts` + `tools/ssh-bash.ts`, `tools/bash.ts`

### Phase 4: Compact
- `context/compact.ts` + `compact-prompts.ts`
- mini_model 生成结构化摘要

---

## 十一、验证方式

### MVP 验证
1. **Executor 测试**：Docker/K8s/SQL/MongoDB 各写一个基础操作的集成测试
2. **Agent 主循环测试**：mock LLM，验证 tool_call → 执行 → 结果追加 → 下一轮
3. **中断恢复测试**：模拟审批中断，验证 saveSession → resumeAgent 链路
4. **端到端**：启动 Agent → 调用 ServiceExec(docker, listContainers) → 返回结果 → 完成

### 后续验证
5. ShellSafety、ServiceSafety 分类器单元测试
6. Compact 压缩和恢复测试
7. Plan Mode 流程测试
