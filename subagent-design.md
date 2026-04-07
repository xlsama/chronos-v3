# Chronos V3 子 Agent 设计文档

> 版本：v1.0
> 日期：2026-04-07
> 参考：Claude Code `AgentTool` / OpenHarness `Swarm`

---

## 一、竞品对比分析

### 1. Claude Code 子 Agent 架构

#### 1.1 核心设计

Claude Code 通过一个叫 `AgentTool` 的工具实现子 Agent。主 Agent 在 `while(true)` 循环中调用 `Agent(...)` 工具，AgentTool 内部启动一个**完整的 query 循环**来运行子 Agent，子 Agent 完成后把结果作为工具返回值传回父 Agent。

```
用户 → 父 Agent (query loop)
           ↓ 调用 Agent(prompt, subagent_type) 工具
       子 Agent (独立的 query loop，独立消息历史)
           ↓ 完成
       返回结果文本给父 Agent（作为 tool_result）
           ↓
       父 Agent 继续对话
```

#### 1.2 输入参数

```typescript
{
  description: string           // 3-5 个字的简短描述
  prompt: string                // 完整的任务指令
  subagent_type?: string        // Agent 类型（"general-purpose" / "Explore" / "Plan"）
  model?: 'sonnet' | 'opus' | 'haiku'
  run_in_background?: boolean   // 后台运行
  isolation?: 'worktree'        // git worktree 隔离
}
```

#### 1.3 Agent 定义

每种 Agent 类型是一个 `.md` 文件 + YAML frontmatter，正文就是系统提示：

```markdown
---
model: haiku
permissionMode: plan
maxTurns: 10
omitClaudeMd: true
tools:
  - Read
  - Grep
  - Glob
---

你是一个专门负责代码探索的 Agent...
```

内置 Agent 类型：
- **general-purpose**：通用 Agent，拥有所有工具
- **Explore**：只读探索 Agent，只有 Read/Grep/Glob 等搜索工具
- **Plan**：架构规划 Agent，只有搜索工具，输出实现计划

#### 1.4 消息隔离

```typescript
// 正常路径：子 Agent 只拿到 prompt 作为初始消息
const initialMessages = [createUserMessage({ content: prompt })]

// Fork 路径：继承父 Agent 的完整消息历史（共享 prompt cache）
const contextMessages = filterIncompleteToolCalls(parentMessages)
```

文件读取缓存也独立：
```typescript
const agentReadFileState = forkContextMessages
  ? cloneFileStateCache(parentCache)  // fork: 克隆父级缓存
  : createNewCache()                  // 正常: 空缓存
```

#### 1.5 同步 vs 异步

| 维度 | 同步子 Agent | 异步子 Agent |
|------|-------------|-------------|
| 执行方式 | 阻塞父 Agent，等待完成 | 立即返回 task ID，后台运行 |
| AbortController | 链接到父级（父中止→子也中止） | 新建独立的 |
| 状态共享 | 共享 AppState | 完全隔离 |
| 权限 | 可弹出交互式确认 | 自动拒绝（无法交互） |
| 返回值 | `{ status: 'completed', result: '...' }` | `{ status: 'async_launched', agentId }` |
| 运行时升级 | 可以在运行中升级为异步 | 原生异步 |

同步执行核心：
```typescript
const agentIterator = runAgent({ ... })[Symbol.asyncIterator]()
const agentMessages = []

while (true) {
  const raceResult = await Promise.race([
    agentIterator.next(),   // 子 Agent 的下一条消息
    backgroundPromise,      // 后台升级信号
  ])
  if (raceResult.done) break
  agentMessages.push(raceResult.value)
}

return { status: 'completed', result: extractTextContent(agentMessages) }
```

#### 1.6 核心优化

- **Prompt Cache 共享**：Fork 子 Agent 使用和父 Agent 完全一样的系统提示前缀 → API 缓存命中 → 降低 token 成本
- **CLAUDE.md 省略**：只读 Agent（Explore/Plan）跳过大型 CLAUDE.md，节省 token
- **gitStatus 省略**：Explore/Plan 移除陈旧的 gitStatus，可以自己运行 `git status`

---

### 2. OpenHarness 子 Agent / Swarm 架构

#### 2.1 核心设计

OpenHarness 采用 **Coordinator-Worker 异步模式**。Coordinator 是一个编排者 Agent，通过 `agent()` 工具生成 Worker Agent。Worker 在后台独立运行，完成后通过消息队列/文件邮箱通知 Coordinator。

```
用户 → Coordinator Agent
           ↓ agent(prompt="排查网络")
       Worker A (asyncio Task)  ← 异步运行
           ↓ agent(prompt="排查数据库")
       Worker B (asyncio Task)  ← 并行运行
           ↓ agent(prompt="排查日志")
       Worker C (asyncio Task)  ← 并行运行
           ↓ Worker 完成，发送 <task-notification>
       Coordinator 收到通知，综合结果
           ↓
       回复用户
```

#### 2.2 输入参数

```python
class AgentToolInput(BaseModel):
    description: str
    prompt: str
    subagent_type: str | None
    model: str | None
    team: str | None
    mode: str = "in_process_teammate"
    # mode: "in_process_teammate" | "local_agent" | "remote_agent"
```

#### 2.3 执行后端

| mode | 实现 | 隔离级别 | 通信方式 |
|------|------|---------|---------|
| `in_process_teammate` | asyncio Task + ContextVar | 线程级 | 内存 Queue |
| `local_agent` | 子进程 (subprocess) | 进程级 | stdin/stdout 管道 |
| `remote_agent` | 远程执行 | 机器级 | HTTP |

#### 2.4 消息隔离 — ContextVar

每个子 Agent 作为 asyncio Task 运行，通过 Python `ContextVar` 实现 per-task 隔离：

```python
_teammate_context: ContextVar[TeammateContext | None] = ContextVar("teammate_context")

class TeammateContext:
    agent_id: str
    agent_name: str
    team_name: str
    abort_controller: TeammateAbortController
    message_queue: asyncio.Queue[TeammateMessage]
    status: "starting" | "running" | "idle" | "stopping" | "stopped"
    tool_use_count: int
    total_tokens: int
```

ContextVar 在 `asyncio.create_task()` 时自动复制，每个 Task 修改互不影响。

#### 2.5 Agent 间通信 — 双通道

**通道一：内存 Queue（In-Process）**
```python
async def send_message(self, agent_id, message):
    ctx = self._contexts[agent_id]
    await ctx.message_queue.put(message)
```

**通道二：文件系统邮箱（跨进程）**
```
~/.openharness/teams/<team>/agents/<agent_id>/inbox/
  1712345678_msg001.json   # 原子写入：.tmp → os.replace()
  1712345679_msg002.json
```

#### 2.6 完成通知格式

Worker 完成后，Coordinator 收到 XML 通知（注入为 user message）：

```xml
<task-notification>
  <task-id>agent-a1b</task-id>
  <status>completed</status>
  <summary>Found null pointer in auth/validate.ts:42</summary>
  <result>完整的排查结果文本...</result>
  <usage>
    <total_tokens>15234</total_tokens>
    <tool_uses>8</tool_uses>
    <duration_ms>12500</duration_ms>
  </usage>
</task-notification>
```

#### 2.7 Coordinator 系统提示核心原则

1. **不要序列化工作** — 独立任务并行启动多个 Worker
2. **Worker 提示必须自包含** — Worker 看不到 Coordinator 的对话历史
3. **具体化指令** — 给 Worker 文件路径、行号、具体改动
4. **理解后再指令** — 不要写"基于你的发现去修复"，要自己综合后给具体指令
5. **Continue vs Spawn** — 高上下文重叠继续现有 Worker，低重叠生成新 Worker

#### 2.8 Abort 控制器 — 双信号

```python
class TeammateAbortController:
    cancel_event: asyncio.Event()     # 优雅关闭（完成当前工具后停止）
    force_cancel: asyncio.Event()     # 强制终止（立即停止）
```

---

### 3. 对比总结

| 维度 | Claude Code | OpenHarness | Chronos 选型 |
|------|-------------|-------------|-------------|
| **执行模式** | 同步为主，可升级异步 | 异步为主（Coordinator-Worker） | **同步** |
| **进程模型** | 单进程 AsyncGenerator | asyncio Task / 子进程 | **单进程** |
| **消息隔离** | 独立 Message[] + 克隆缓存 | ContextVar + Queue | **独立 Message[]** |
| **工具过滤** | 按 Agent 定义过滤 | 按 Agent 定义过滤 | **按 readOnly 过滤** |
| **Agent 间通信** | 同步直接返回 / 异步 TaskGet | Queue + 文件邮箱 | **同步直接返回** |
| **完成通知** | 工具返回值 / enqueueNotification | XML `<task-notification>` | **工具返回值** |
| **缓存优化** | Fork 共享 prompt cache | 无 | **不适用**（DashScope 无 cache） |
| **并行子 Agent** | 异步模式 + background | asyncio.gather | **Promise.allSettled** |
| **Abort** | 链接到父级 AbortController | 双信号（优雅+强制） | **链接到父级 signal** |
| **Agent 定义** | .md + YAML frontmatter | .md + YAML frontmatter | **暂不需要**（固定 2 种类型） |

---

## 二、Chronos V3 子 Agent 需求设计

### 1. 设计目标

在运维排查场景下，子 Agent 的核心价值：

1. **并行假设验证** — 主 Agent 有多个排查假设（网络？数据库？磁盘？），fork 多个子 Agent 同时排查
2. **只读验证** — 执行修复后，派一个只读子 Agent 验证问题是否解决
3. **深度聚焦** — 主 Agent 负责全局调度，子 Agent 负责某一具体方向的深度排查

**不做的事情**：
- 不做异步后台模式（SSE 流式 API 不需要）
- 不做 Agent 定义文件（.md frontmatter）（固定 2 种类型足够）
- 不做 prompt cache 优化（DashScope 不支持）
- 不做文件系统邮箱（同步执行，不需要跨进程通信）
- 不做 Coordinator 模式（主 Agent 就是 Coordinator）

### 2. 架构概览

```
主 Agent (runAgent, while true 循环)
  │
  ├─ 调用 sub_agent(task, readOnly) 工具
  │     └→ runSubAgent()  — 简化版 agent loop
  │          ├─ 独立 Message[]（消息隔离）
  │          ├─ 过滤后的 ToolRegistry（readOnly 过滤）
  │          ├─ 子 Agent 专用系统提示
  │          ├─ 不写 DB，不发 SSE
  │          └→ 返回 SubAgentResult（summary 文本）
  │
  └─ 调用 parallel_investigate(hypotheses) 工具
        └→ Promise.allSettled([
             runSubAgent(hypothesis1),
             runSubAgent(hypothesis2),
             runSubAgent(hypothesis3),
           ])
        └→ 返回合并报告
```

### 3. 类型定义

```typescript
// ─── server/src/ops-agent/types.ts（新增） ────────────

export interface SubAgentConfig {
  /** 子 Agent 的具体排查任务 */
  task: string;
  /** 是否只读模式（只允许 read 类操作） */
  readOnly: boolean;
  /** 最大轮次，默认 15 */
  maxTurns?: number;
}

export interface SubAgentResult {
  /** 子 Agent 唯一 ID */
  agentId: string;
  /** 任务描述 */
  task: string;
  /** 终止状态 */
  status: "completed" | "failed" | "max_turns";
  /** 最终总结文本 */
  summary: string;
  /** 实际执行轮次 */
  turnCount: number;
  /** 总 token 估算 */
  estimatedTokens: number;
}
```

### 4. 核心实现：`runSubAgent()`

```typescript
// ─── server/src/ops-agent/sub-agent.ts ──────────────

/**
 * 运行一个子 Agent。
 *
 * 设计原则（参考 Claude Code runAgent.ts）：
 * 1. 独立 Message[] — 子 Agent 看不到父 Agent 的对话历史
 * 2. 工具过滤 — readOnly 时只保留只读工具
 * 3. 不写 DB — 子 Agent 的会话不持久化（只存在于内存）
 * 4. 不发 SSE — 子 Agent 的事件不暴露给前端
 * 5. 继承父 session 的 planMd — 让子 Agent 了解排查上下文
 */
export async function runSubAgent(
  parentSession: AgentSession,
  config: SubAgentConfig,
  signal?: AbortSignal,
): Promise<SubAgentResult>
```

#### 4.1 执行流程

```
runSubAgent(parentSession, { task, readOnly, maxTurns })
  │
  ├─ 1. 生成子 Agent ID（nanoid）
  │
  ├─ 2. 构建工具列表
  │     ├─ readOnly=true  → 只保留 search_knowledge, search_incidents, bash(只读命令)
  │     │                    service_exec(只读操作), use_skill
  │     │                    排除 update_plan, ask_user_question
  │     └─ readOnly=false → 保留所有工具，排除 ask_user_question, sub_agent（防递归）
  │
  ├─ 3. 构建系统提示
  │     ├─ 子 Agent 基础提示（聚焦于单一任务）
  │     ├─ 父 session 的 planMd（提供全局上下文）
  │     └─ 可用资源列表（servers/services）
  │
  ├─ 4. 初始化消息
  │     └─ [{ role: "user", content: task }]
  │
  ├─ 5. while (true) 循环（简化版，参考主 agent-loop）
  │     ├─ 检查 signal?.aborted
  │     ├─ 检查 turnCount > maxTurns
  │     ├─ 调用 generateText（和主 Agent 同模型）
  │     ├─ 处理 toolCalls（直接执行，无权限检查弹窗）
  │     │   ├─ readOnly 模式下 write/dangerous → 自动拒绝（返回错误消息）
  │     │   └─ 只读操作 → 直接执行
  │     └─ 无 toolCalls → 完成
  │
  └─ 6. 返回 SubAgentResult
        ├─ summary = 最后一条 assistant 消息
        ├─ status = "completed" | "failed" | "max_turns"
        └─ turnCount, estimatedTokens
```

#### 4.2 工具过滤策略

```typescript
function buildSubAgentTools(
  allTools: ToolDefinition[],
  readOnly: boolean,
): ToolDefinition[] {
  // 始终排除的工具（防递归、防中断）
  const EXCLUDED = new Set(["sub_agent", "parallel_investigate", "ask_user_question"]);

  const filtered = allTools.filter(t => !EXCLUDED.has(t.name));

  if (!readOnly) return filtered;

  // readOnly 模式：包装 bash 和 service_exec 的 execute，
  // 在执行前检查权限，非 read 类型直接返回错误
  return filtered.map(t => {
    if (t.name === "bash" || t.name === "service_exec") {
      return wrapReadOnlyExecute(t);
    }
    // search_knowledge, search_incidents, use_skill — 天然只读
    // update_plan — 允许（只是更新内存中的计划）
    return t;
  });
}

function wrapReadOnlyExecute(tool: ToolDefinition): ToolDefinition {
  return {
    ...tool,
    execute: async (args) => {
      // 复用现有 classifier 判断命令类型
      const perm = await tool.checkPermission?.(args);
      if (perm && perm.behavior !== "allow") {
        return `[只读模式] 操作被拒绝: ${perm.reason}。子 Agent 只能执行只读操作。`;
      }
      return tool.execute(args);
    },
  };
}
```

#### 4.3 子 Agent 系统提示

```typescript
// ─── server/src/ops-agent/context/sub-agent-prompts.ts ──────

export function getSubAgentSystemPrompt(
  parentSession: AgentSession,
  config: SubAgentConfig,
): string {
  const parts: string[] = [SUB_AGENT_BASE_PROMPT];

  if (config.readOnly) {
    parts.push(READ_ONLY_CONSTRAINT);
  }

  // 继承父 session 的调查计划（提供全局上下文）
  if (parentSession.planMd) {
    parts.push(`\n## 当前调查计划（主 Agent 制定）\n\n${parentSession.planMd}`);
  }

  // 注入可用资源
  const resources = await getAvailableResources();
  if (resources) parts.push(resources);

  return parts.join("\n");
}

const SUB_AGENT_BASE_PROMPT = `你是一个运维排查子 Agent。你的任务是聚焦于**一个具体的排查方向**，深入调查并给出结论。

## 工作要求

1. 专注于分配给你的具体任务，不要发散到其他方向
2. 使用 search_knowledge 和 search_incidents 收集背景信息
3. 使用 service_exec 或 bash 执行诊断命令
4. 发现关键证据后立即记录
5. 完成后输出简洁的结论，包含：
   - 排查了什么
   - 发现了什么（关键证据）
   - 结论（是否是根因，或排除了这个方向）
6. 保持简洁，不要重复已知信息`;

const READ_ONLY_CONSTRAINT = `
## 只读限制

你处于只读验证模式。你只能执行读取操作（查看日志、状态、配置等），不能执行任何写操作（重启、删除、修改等）。
如果需要写操作才能进一步排查，请在结论中说明。`;
```

#### 4.4 权限处理（与主 Agent 的区别）

| 场景 | 主 Agent | 子 Agent |
|------|---------|---------|
| read 操作 | allow | allow |
| write 操作 | ask（弹审批） | readOnly ? 自动拒绝 : allow |
| dangerous 操作 | ask（弹审批） | readOnly ? 自动拒绝 : allow |
| blocked 操作 | deny | deny |
| ask_user_question | 中断等用户回复 | **不可用**（工具已排除） |

子 Agent **不走审批流程**。原因：
1. 子 Agent 是同步执行的，中断等审批会阻塞主 Agent
2. readOnly 子 Agent 天然不需要写操作
3. 非 readOnly 子 Agent 由主 Agent 主动调用，视为已授权

### 5. `sub_agent` Tool 定义

```typescript
// ─── server/src/ops-agent/tools/sub-agent.ts ──────────

import { z } from "zod";
import type { ToolDefinition } from "../types";
import { runSubAgent } from "../sub-agent";

export const subAgentTool: ToolDefinition = {
  name: "sub_agent",
  description:
    "启动一个子 Agent 执行特定的排查任务。子 Agent 有独立的上下文，" +
    "不会看到你的对话历史。适合：(1) 深入排查某个特定方向 " +
    "(2) 验证修复是否生效（readOnly 模式）。" +
    "注意：子 Agent 无法向用户提问，也无法触发审批。",
  parameters: z.object({
    task: z.string().describe(
      "子 Agent 的具体排查任务。必须是自包含的指令，包含：" +
      "排查什么、使用哪个 service、预期找什么证据。" +
      "子 Agent 看不到你的对话历史，所以要把必要上下文写在这里。"
    ),
    readOnly: z.boolean().default(true).describe(
      "是否只读模式。true = 只能执行读取操作，适合验证场景；" +
      "false = 可以执行写操作，适合需要修改的排查"
    ),
  }),
  needsPermissionCheck: false,
  maxResultChars: 8_000,

  execute: async (args) => {
    // parentSession 通过闭包或参数注入
    // 这里先写伪代码，实现时再确定注入方式
    const result = await runSubAgent(parentSession, {
      task: args.task,
      readOnly: args.readOnly,
      maxTurns: 15,
    });

    return formatSubAgentResult(result);
  },
};

function formatSubAgentResult(result: SubAgentResult): string {
  const statusMap = {
    completed: "完成",
    failed: "失败",
    max_turns: "达到最大轮次",
  };
  return [
    `<sub-agent-result>`,
    `状态: ${statusMap[result.status]}`,
    `轮次: ${result.turnCount}`,
    `---`,
    result.summary,
    `</sub-agent-result>`,
  ].join("\n");
}
```

### 6. `parallel_investigate` Tool 定义

```typescript
// ─── server/src/ops-agent/tools/parallel-investigate.ts ──

import { z } from "zod";
import type { ToolDefinition } from "../types";
import { runSubAgent } from "../sub-agent";

export const parallelInvestigateTool: ToolDefinition = {
  name: "parallel_investigate",
  description:
    "并行启动多个子 Agent，同时验证多个排查假设。" +
    "每个假设由一个独立的只读子 Agent 执行，互不干扰。" +
    "所有子 Agent 完成后返回合并报告。适合：" +
    "有 2-5 个排查方向需要同时验证时。",
  parameters: z.object({
    hypotheses: z.array(z.object({
      name: z.string().describe("假设名称，如 '网络连通性' 或 '数据库慢查询'"),
      task: z.string().describe("具体的排查指令（自包含，包含必要上下文）"),
    })).min(1).max(5).describe("要并行验证的假设列表，最多 5 个"),
  }),
  needsPermissionCheck: false,
  maxResultChars: 16_000,

  execute: async (args) => {
    const results = await Promise.allSettled(
      args.hypotheses.map((h) =>
        runSubAgent(parentSession, {
          task: h.task,
          readOnly: true,
          maxTurns: 15,
        })
      ),
    );

    return formatParallelResults(args.hypotheses, results);
  },
};

function formatParallelResults(
  hypotheses: { name: string; task: string }[],
  results: PromiseSettledResult<SubAgentResult>[],
): string {
  const parts: string[] = ["<parallel-investigation-report>"];

  for (let i = 0; i < hypotheses.length; i++) {
    const h = hypotheses[i];
    const r = results[i];

    parts.push(`\n## 假设 ${i + 1}: ${h.name}`);

    if (r.status === "fulfilled") {
      const statusMap = { completed: "完成", failed: "失败", max_turns: "达到最大轮次" };
      parts.push(`状态: ${statusMap[r.value.status]} | 轮次: ${r.value.turnCount}`);
      parts.push(r.value.summary);
    } else {
      parts.push(`状态: 执行异常`);
      parts.push(`错误: ${r.reason?.message ?? String(r.reason)}`);
    }
  }

  parts.push("\n</parallel-investigation-report>");
  return parts.join("\n");
}
```

### 7. 事件系统扩展

```typescript
// ─── types.ts AgentEvent 新增 ────────────────────────

| { type: "sub_agent_start"; data: {
    agentId: string;
    task: string;
    readOnly: boolean;
  } }
| { type: "sub_agent_done"; data: {
    agentId: string;
    status: string;
    summary: string;
    turnCount: number;
  } }

// ─── publisher.ts 新增 ──────────────────────────────

subAgentStart(agentId: string, task: string, readOnly: boolean): AgentEvent
subAgentDone(agentId: string, status: string, summary: string, turnCount: number): AgentEvent
```

> 注意：虽然子 Agent 不直接发 SSE，但主 Agent 在调用 sub_agent 工具前后可以 yield 这些事件，让前端知道子 Agent 在运行。

### 8. 并发分类

```typescript
// ─── tools/concurrency.ts 修改 ───────────────────────

const ALWAYS_SERIAL = new Set(["update_plan", "sub_agent", "parallel_investigate"]);
// sub_agent: 串行（同步执行，阻塞主循环）
// parallel_investigate: 串行（内部自己并行）
```

### 9. System Prompt 修改

在主 Agent 的 `BASE_PROMPT` 中增加子 Agent 使用指南：

```
## 子 Agent

当排查方向不确定时，你可以启动子 Agent 来并行验证多个假设：

- sub_agent: 启动一个子 Agent 执行特定排查任务
  - readOnly=true: 只读模式，适合验证（日志检查、状态查看等）
  - readOnly=false: 可写模式，适合需要修改的排查
  - 子 Agent 看不到你的对话历史，task 必须是自包含的指令

- parallel_investigate: 并行启动多个只读子 Agent 验证不同假设
  - 适合有 2-5 个排查方向需要同时验证的场景
  - 所有子 Agent 完成后返回合并报告

### 使用原则

1. 子 Agent 的 task 必须自包含 — 包含目标、使用哪个 service、预期找什么证据
2. 先自己收集基础信息，再决定是否需要子 Agent — 不要一上来就并行
3. 并行验证适合"排除法" — 多个可能的根因同时检查
4. 验证修复效果时用 readOnly 子 Agent — 确保不会引入新的变更
5. 不要嵌套子 Agent — 子 Agent 不能再启动子 Agent
```

---

## 三、文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `server/src/ops-agent/sub-agent.ts` | 核心：`runSubAgent()` 简化版 agent loop |
| `server/src/ops-agent/tools/sub-agent.ts` | `sub_agent` 工具定义 |
| `server/src/ops-agent/tools/parallel-investigate.ts` | `parallel_investigate` 工具定义 |
| `server/src/ops-agent/context/sub-agent-prompts.ts` | 子 Agent 系统提示 |
| `server/tests/ops-agent/sub-agent.test.ts` | 单元测试 |
| `server/tests/ops-agent/parallel-investigate.test.ts` | 单元测试 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `server/src/ops-agent/types.ts` | 新增 `SubAgentConfig`, `SubAgentResult`, 2 个 AgentEvent |
| `server/src/ops-agent/tools/registry.ts` | 注册 `subAgentTool`, `parallelInvestigateTool` |
| `server/src/ops-agent/tools/concurrency.ts` | ALWAYS_SERIAL 新增两个工具 |
| `server/src/ops-agent/events/publisher.ts` | 新增 `subAgentStart()`, `subAgentDone()` |
| `server/src/ops-agent/context/system-prompt.ts` | BASE_PROMPT 增加子 Agent 使用指南 |

---

## 四、测试方案

### 单元测试

```typescript
// sub-agent.test.ts

describe("runSubAgent", () => {
  it("应该用独立消息历史运行子 Agent", async () => {
    // mock generateText 返回一个 assistant 回复（无 tool calls）
    // 验证子 Agent 的消息不包含父 session 的历史
  });

  it("readOnly 模式应该拒绝写操作", async () => {
    // mock generateText 返回 bash tool call: "rm -rf /tmp/test"
    // 验证子 Agent 返回拒绝消息，不执行命令
  });

  it("readOnly 模式应该允许读操作", async () => {
    // mock generateText 返回 bash tool call: "ls /tmp"
    // 验证子 Agent 正常执行
  });

  it("应该在达到 maxTurns 时终止", async () => {
    // mock generateText 始终返回 tool calls
    // 验证在 maxTurns 后终止，status = "max_turns"
  });

  it("应该继承父 session 的 planMd", async () => {
    // 验证子 Agent 的系统提示包含父 session 的 planMd
  });

  it("应该排除 sub_agent 工具（防递归）", async () => {
    // 验证子 Agent 的工具列表不包含 sub_agent 和 parallel_investigate
  });

  it("应该排除 ask_user_question 工具", async () => {
    // 验证子 Agent 的工具列表不包含 ask_user_question
  });

  it("应该响应 abort signal", async () => {
    // 传入已中止的 signal
    // 验证子 Agent 立即返回 status = "failed"
  });
});

// parallel-investigate.test.ts

describe("parallel_investigate", () => {
  it("应该并行执行多个假设", async () => {
    // mock runSubAgent（每个延迟 100ms）
    // 3 个假设应该在 ~100ms 完成（而非 300ms）
  });

  it("单个子 Agent 失败不影响其他", async () => {
    // mock 第 2 个子 Agent 抛异常
    // 验证其他 2 个正常返回
  });

  it("应该合并所有结果", async () => {
    // 验证返回格式包含所有假设的结果
  });

  it("最多 5 个假设", async () => {
    // 验证 Zod schema 拒绝 > 5 个假设
  });
});
```

### 集成测试

```typescript
// E2E: 主 Agent 使用子 Agent 排查

describe("Agent with sub-agent", () => {
  it("主 Agent 应该能调用 sub_agent 并使用结果", async () => {
    // 1. 创建 incident
    // 2. runAgent(incidentId, "CPU 使用率过高，请排查")
    // 3. 验证 agent 在排查过程中调用了 sub_agent 或 parallel_investigate
    // 4. 验证最终总结包含子 Agent 的发现
  });
});
```

---

## 五、关键设计决策及理由

| 决策 | 选择 | 理由 |
|------|------|------|
| 同步 vs 异步 | **同步** | Chronos 是 SSE 流式 API，子 Agent 结果需要立即返回给主 Agent 继续推理。异步模式增加了消息路由和通知机制的复杂度，收益不明显 |
| 消息隔离方式 | **独立 Message[]** | 最简单有效。子 Agent 在函数内部维护自己的消息数组，函数返回后消息自然释放。不需要 ContextVar（Bun 单线程） |
| 子 Agent 是否持久化 | **不持久化** | 子 Agent 是临时的、短暂的。它的结果通过工具返回值融入主 Agent 的消息历史，不需要独立存储 |
| 权限处理 | **readOnly 自动拒绝，非 readOnly 自动允许** | 子 Agent 不能弹审批（会阻塞主 Agent）。readOnly 模式本身就是安全约束，非 readOnly 是主 Agent 主动选择 |
| 是否支持嵌套子 Agent | **不支持** | 从工具列表中排除 sub_agent，防止递归。运维场景下一层子 Agent 足够 |
| maxTurns | **默认 15** | 子 Agent 是聚焦任务，不需要主 Agent 的 40 轮。15 轮足够完成一个方向的排查 |
| 并行上限 | **最多 5 个** | Zod schema 限制。过多子 Agent 并行会导致 API 请求并发过高，增加费用 |
| 子 Agent 模型 | **和主 Agent 相同** | 简化实现。未来可以加 model override（如用 mini_model 做简单验证） |
