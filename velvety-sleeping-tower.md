# Chronos V3 Ops AI Agent — 下一阶段完整优化计划

> 参考：Claude Code / OpenHarness / Dify
> 当前已完成：MVP + Phase 1-5（含并发调度、磁盘持久化、Embedding 缓存、Token 估算）

---

## Context

Chronos V3 已完成核心 Agent 循环、7 个工具、5 种 Executor、安全分类、Compact、并发调度等功能。对比 Claude Code 和 OpenHarness，主要缺失：

1. **子 Agent** — 无法并行验证多个假设，无法 fork 只读验证 Agent
2. **Skills 运行时集成** — 已有 `service/skill.ts` CRUD + 文件系统存储，但 Agent 无法在排查中发现和使用 Skill
3. **Microcompact** — 只有 LLM 摘要一层 compact，缺少廉价的旧工具结果清理层
4. **Memory** — 跨 session 知识丢失，每次从零开始
5. **Tool prompt()** — 工具描述是静态的，缺少动态使用指南
6. **Hooks** — 无扩展点，无法在工具执行前后注入自定义逻辑
7. **成本追踪** — 无 token 用量和费用记录

---

## Phase 6: 子 Agent 系统

### 6.1 单个子 Agent（`sub_agent` Tool）

**新增文件：**

- `server/src/ops-agent/sub-agent.ts` — 核心运行函数

```typescript
// 简化版 agent loop，内存运行，不持久化
export async function runSubAgent(
  parentSession: AgentSession,
  config: SubAgentConfig,
): Promise<SubAgentResult>
```

设计要点：
- 复用 `generateText` + `buildToolRegistry()` 但**过滤工具**（readOnly 时只保留 read 类工具）
- 独立 `Message[]`（消息隔离），不写 DB，不发 SSE
- 继承父 session 的 `planMd` 作为背景上下文
- `maxTurns` 默认 15（比主 Agent 的 40 小）
- 无 interrupt/approval 流程 — readOnly 子 Agent 遇到 ask 直接 deny

- `server/src/ops-agent/tools/sub-agent.ts` — Tool 定义

```typescript
schema = z.object({
  task: z.string().describe("子 Agent 的具体排查任务"),
  readOnly: z.boolean().default(true).describe("是否只读模式"),
})
```

- `server/src/ops-agent/context/sub-agent-prompts.ts` — 子 Agent 系统提示

**修改文件：**

| 文件 | 改动 |
|------|------|
| `types.ts` | 新增 `SubAgentConfig`, `SubAgentResult`, `sub_agent_start/done` 事件 |
| `tools/registry.ts` | 注册 `subAgentTool` |
| `tools/concurrency.ts` | `sub_agent` → `ALWAYS_SERIAL` |
| `events/publisher.ts` | 新增 `subAgentStart()`, `subAgentDone()` |
| `context/system-prompt.ts` | BASE_PROMPT 增加子 Agent 使用指南 |

### 6.2 并行假设验证（`parallel_investigate` Tool）

**新增文件：**

- `server/src/ops-agent/tools/parallel-investigate.ts`

```typescript
schema = z.object({
  hypotheses: z.array(z.object({
    name: z.string(),
    task: z.string(),
  })).min(1).max(5),
})

// execute: Promise.allSettled(hypotheses.map(h => runSubAgent(...)))
// 返回合并报告
```

**修改：** `tools/registry.ts` 注册，`concurrency.ts` → `ALWAYS_SERIAL`（内部自己并行）

### 6.3 测试

- `server/tests/ops-agent/sub-agent.test.ts` — mock generateText，验证消息隔离、readOnly 过滤、maxTurns 限制
- `server/tests/ops-agent/parallel-investigate.test.ts` — 多假设并行，结果合并

---

## Phase 7: Skills 运行时集成

### 现状

已有完整的 Skill CRUD 服务（`server/src/service/skill.ts`）：
- 文件系统存储：`data/skills/{slug}/SKILL.md`
- YAML frontmatter：`name, description, when_to_use, tags, related_services, draft`
- 子目录支持：`scripts/, references/, assets/`
- RPC 端点：`server/src/rpc/skill.ts`

**缺失：Agent 运行时无法发现和使用 Skill**

### 7.1 use_skill Tool

**新增文件：**

- `server/src/ops-agent/tools/use-skill.ts`

```typescript
import { listSkills, getSkill, readSkillFile } from "../../service/skill";

schema = z.object({
  skill: z.string().describe("Skill 的 slug"),
  args: z.string().optional().describe("额外参数"),
})

// execute:
// 1. getSkill(slug) → { meta, content }
// 2. 如果有 scripts/，列出可用脚本
// 3. 如果有 references/，列出参考文档
// 4. 返回 Skill 完整内容 + 脚本列表 + 参考列表
```

- `server/src/ops-agent/context/skill-loader.ts`

```typescript
import { listSkills } from "../../service/skill";

// 加载非 draft 的 Skills，构建 system prompt 段落
export async function loadAvailableSkills(): Promise<SkillSummary[]>
export function buildSkillsPromptSection(skills: SkillSummary[]): string
```

输出格式：
```
## 可用 Skills

以下 Skills 包含预定义的排查流程，使用 use_skill 工具加载：
- log-analysis: Docker 容器日志分析排查流程 (when: 当用户报告容器错误或异常日志时)
- performance-diagnosis: CPU/内存/IO 性能诊断 (when: 当出现性能问题时)
```

**修改文件：**

| 文件 | 改动 |
|------|------|
| `tools/registry.ts` | 注册 `useSkillTool` |
| `tools/concurrency.ts` | `use_skill` → `ALWAYS_CONCURRENT`（只读） |
| `context/system-prompt.ts` | `getSystemPrompt()` 中调用 `loadAvailableSkills()` + `buildSkillsPromptSection()` |

### 7.2 内置 Skills（种子数据）

在 `seeds/skills/` 下创建 6 个运维 Skill：

| Skill | 内容 |
|-------|------|
| `log-analysis` | 容器日志分析：获取日志 → 关键词过滤 → 时间线排查 → 根因定位 |
| `performance-diagnosis` | 性能诊断：CPU/Memory/IO/Network 四维排查流程 |
| `network-diagnosis` | 网络诊断：连通性检测 → DNS → 端口 → 防火墙 → 路由 |
| `database-slow-query` | 慢查询分析：识别慢 SQL → EXPLAIN → 索引建议 → 连接池检查 |
| `container-health-check` | 容器健康检查：状态 → 资源 → 日志 → 配置 → 依赖 |
| `k8s-pod-troubleshoot` | K8s Pod 排查：Events → Describe → Logs → 资源配额 → 调度 |

每个 SKILL.md 格式：
```markdown
---
name: log-analysis
description: "Docker 容器日志分析排查流程"
when_to_use: "当用户报告容器错误、服务异常、应用崩溃时"
tags: docker, logs, troubleshoot
related_services: docker
draft: false
---

# Docker 日志分析

## 第一步：确认容器状态
使用 service_exec 的 listContainers 查看所有容器...

## 第二步：获取容器日志
...
```

### 7.3 测试

- `server/tests/ops-agent/use-skill.test.ts` — 加载 Skill、列出 Skill、系统提示注入
- seed 脚本验证：确认 seeds/skills/ 下的 SKILL.md 格式正确

---

## Phase 8: 上下文优化

### 8.1 Microcompact（廉价清理层，无 LLM 调用）

参考 OpenHarness 的 microcompact：清理旧的工具结果内容，保留最近几条。

**新增文件：**

- `server/src/ops-agent/context/microcompact.ts`

```typescript
const COMPACTABLE_TOOLS = new Set([
  "bash", "service_exec", "search_knowledge", "search_incidents",
]);
const MICROCOMPACT_TOKEN_THRESHOLD = 25_000;
const KEEP_RECENT_TOOL_RESULTS = 6;
const CLEARED_MSG = "[旧工具结果已清理，如需查看请参考历史摘要]";

export function shouldMicrocompact(messages: Message[]): boolean {
  return estimateMessagesTokens(messages) > MICROCOMPACT_TOKEN_THRESHOLD;
}

export function microcompactMessages(messages: Message[]): {
  messages: Message[];
  tokensSaved: number;
} {
  // 1. 收集所有 compactable tool result 消息的索引
  // 2. 保留最近 KEEP_RECENT_TOOL_RESULTS 条
  // 3. 更早的替换为 CLEARED_MSG
  // 4. 返回修改后的消息和节省的 token 数
}
```

**修改 `agent-loop.ts`：**

在现有的 compact 检查之前插入 microcompact：

```typescript
// 2a. Microcompact（廉价，无 LLM）
if (shouldMicrocompact(session.agentMessages)) {
  const { messages, tokensSaved } = microcompactMessages(session.agentMessages);
  if (tokensSaved > 0) {
    session.agentMessages = messages;
    yield pub.microcompactDone(tokensSaved);
  }
}

// 2b. Full compact（原有逻辑不变）
if (shouldCompact(session.agentMessages)) { ... }
```

**修改 `events/publisher.ts`：** 新增 `microcompactDone(tokensSaved)` 事件
**修改 `types.ts`：** AgentEvent 新增 `microcompact_done`

### 8.2 Tool prompt() 动态使用指南

**修改 `types.ts`：**

```typescript
export interface ToolDefinition<TArgs = unknown> {
  // ... 现有字段
  prompt?: () => string;  // 动态使用指南，注入 system prompt
}
```

**为关键工具添加 prompt()：**

- `tools/bash.ts`:
  ```
  常用诊断命令：
  - 进程: ps aux | grep ..., top -b -n 1
  - 网络: curl -s http://..., netstat -tlnp, ping -c 3
  - 磁盘: df -h, du -sh /path
  - 日志: tail -n 100 /var/log/...
  ```

- `tools/service-exec.ts`:
  ```
  各 service type 支持的操作：
  - docker: listContainers, inspectContainer, containerLogs, stats...
  - kubernetes: listPods, describePod, getPodLogs, listDeployments...
  - postgresql/mysql: executeSql, listTables, describeTable...
  - mongodb: findDocuments, aggregate, countDocuments...
  ```

**修改 `context/system-prompt.ts`：**

```typescript
function getToolPrompts(tools: ToolDefinition[]): string {
  return tools
    .filter(t => t.prompt)
    .map(t => `### ${t.name}\n${t.prompt!()}`)
    .join("\n\n");
}

// 在 getSystemPrompt() 中：
const toolPrompts = getToolPrompts(tools);
if (toolPrompts) parts.push(`\n## 工具使用指南\n\n${toolPrompts}`);
```

注意：需要给 `getSystemPrompt` 传入 tools 参数。

### 8.3 Memory 系统（跨 Session 持久化记忆）

**新增 DB 表** — `server/src/db/schema.ts`：

```typescript
export const agentMemories = pgTable("agent_memories", {
  id: uuid("id").primaryKey().defaultRandom(),
  title: varchar("title", { length: 500 }).notNull(),
  content: text("content").notNull(),
  source: varchar("source", { length: 20 }).notNull().default("agent"),
  incidentId: uuid("incident_id").references(() => incidents.id),
  tags: jsonb("tags").$type<string[]>().notNull().default([]),
  embedding: vector("embedding", { dimensions: 1024 }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
```

**新增文件：**

- `server/src/ops-agent/memory/manager.ts`

```typescript
import { embedTexts } from "../../lib/embedder";
import { db } from "../../db/connection";
import { agentMemories } from "../../db/schema";

export async function searchMemories(query: string, limit = 5): Promise<MemoryEntry[]>
// 使用向量相似度搜索 agentMemories 表

export async function saveMemory(entry: { title, content, source, incidentId?, tags? }): Promise<string>
// embedding + 存 DB

export async function listRecentMemories(limit = 10): Promise<MemoryEntry[]>
// 按 createdAt 降序
```

- `server/src/ops-agent/tools/save-memory.ts`

```typescript
schema = z.object({
  title: z.string().describe("记忆标题，简洁概括"),
  content: z.string().describe("记忆内容，包含关键发现和解决方案"),
  tags: z.array(z.string()).optional(),
})
```

**修改 `context/system-prompt.ts`：**

Session 开始时查询相关记忆：
```typescript
const memories = await searchMemories(initialPrompt, 3);
if (memories.length > 0) {
  parts.push(`\n## 相关历史记忆\n\n${memories.map(m =>
    `### ${m.title}\n${m.content}`
  ).join("\n\n")}`);
}
```

**修改 `agent-loop.ts`：** Agent 完成时提示自动保存记忆（在 `done` 之前，让 LLM 判断是否值得记忆）

### 8.4 测试

- `server/tests/ops-agent/unit/microcompact.test.ts` — 阈值判断、消息清理、token 节省计算
- `server/tests/ops-agent/memory.test.ts` — 保存、搜索、列表
- `server/tests/ops-agent/tool-prompts.test.ts` — prompt() 输出格式

---

## Phase 9: Hooks 系统

### 9.1 核心实现

参考 OpenHarness 的 Hook 机制，简化为 command + http 两种类型。

**新增文件：**

- `server/src/ops-agent/hooks/types.ts`

```typescript
export type HookEvent = "pre_tool_use" | "post_tool_use" | "session_start" | "session_end";

export interface HookDefinition {
  event: HookEvent;
  type: "command" | "http";
  toolNamePattern?: string;   // glob，如 "bash" 或 "service_exec"
  // command 类型
  command?: string;
  // http 类型
  url?: string;
  method?: string;            // 默认 POST
  headers?: Record<string, string>;
  // 通用
  timeout?: number;           // ms，默认 5000
  blocking?: boolean;         // pre_tool_use 时可阻止执行
}

export interface HookResult {
  success: boolean;
  output: string;
  blocked: boolean;
  reason: string;
}
```

- `server/src/ops-agent/hooks/registry.ts`

```typescript
export class HookRegistry {
  private hooks = new Map<HookEvent, HookDefinition[]>();
  register(hook: HookDefinition): void
  getHooks(event: HookEvent, toolName?: string): HookDefinition[]
}

// 从 data/hooks.json 加载配置
export async function loadHooksFromConfig(): Promise<HookRegistry>
```

- `server/src/ops-agent/hooks/executor.ts`

```typescript
export class HookExecutor {
  constructor(private registry: HookRegistry) {}

  async execute(event: HookEvent, payload: Record<string, unknown>): Promise<{
    blocked: boolean;
    reason: string;
  }>

  private async runCommandHook(hook: HookDefinition, payload: Record<string, unknown>): Promise<HookResult>
  // Bun.spawn, env 注入 CHRONOS_HOOK_EVENT + CHRONOS_HOOK_PAYLOAD

  private async runHttpHook(hook: HookDefinition, payload: Record<string, unknown>): Promise<HookResult>
  // ofetch POST/GET
}
```

**修改 `agent-loop.ts`：**

```typescript
// 初始化
const hookExecutor = new HookExecutor(await loadHooksFromConfig());
await hookExecutor.execute("session_start", { incidentId, sessionId: session.id });

// 工具执行前（串行批次中）
const preResult = await hookExecutor.execute("pre_tool_use", {
  toolName: tc.name, toolArgs: tc.args, incidentId,
});
if (preResult.blocked) {
  session.agentMessages.push({ role: "tool", toolCallId: tc.id, toolName: tc.name,
    content: `Hook 阻止执行: ${preResult.reason}` });
  yield pub.toolDenied(tc.name, `Hook blocked: ${preResult.reason}`);
  continue;
}

// 工具执行后
await hookExecutor.execute("post_tool_use", {
  toolName: tc.name, toolArgs: tc.args, toolResult: output, incidentId,
});

// session 结束
await hookExecutor.execute("session_end", { incidentId, sessionId: session.id, status: session.status });
```

### 9.2 测试

- `server/tests/ops-agent/hooks.test.ts` — registry 注册/匹配、command hook 执行、blocking 行为、timeout

---

## Phase 10: 其他优化

### 10.1 API 重试（低工作量，高价值）

**新增文件：**

- `server/src/lib/api-retry.ts`

```typescript
import pRetry from "p-retry";

export function withLLMRetry<T>(fn: () => Promise<T>, retries = env.API_RETRIES): Promise<T> {
  return pRetry(fn, {
    retries,
    onFailedAttempt: (err) => {
      // 只重试 429/500/502/503
      if (!isRetryableError(err)) throw err;
      log.warn(`LLM retry ${err.attemptNumber}/${retries}: ${err.message}`);
    },
  });
}
```

**修改：**
- `agent-loop.ts` — `generateText` 包装 `withLLMRetry`
- `context/compact.ts` — compact 的 `generateText` 包装
- `context/title-generator.ts` — 标题生成包装

### 10.2 成本追踪

**新增文件：**

- `server/src/ops-agent/context/cost-tracker.ts`

```typescript
export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  model: string;
}

export class CostTracker {
  private usages: TokenUsage[] = [];
  record(usage: TokenUsage): void
  getTotal(): { inputTokens: number; outputTokens: number }
}
```

**修改：**
- `types.ts` — AgentSession 新增 `tokenUsage` 字段，AgentEvent 新增 `cost_summary`
- `db/schema.ts` — agentSessions 表新增 `tokenUsage` JSONB 列
- `agent-loop.ts` — 每次 `generateText` 后 `costTracker.record(result.usage)`，session 结束时 `yield pub.costSummary(total)`
- `events/publisher.ts` — 新增 `costSummary()` 方法

### 10.3 检索优化（延后，按需）

- 元数据过滤：`hybrid-search.ts` 增加 `metadataFilter` 参数
- 中文分词词库：给 jieba-wasm 添加运维领域词汇

---

## 总优先级排序

| 优先级 | 内容 | 工作量 | 影响 |
|--------|------|--------|------|
| **P0** | 8.1 Microcompact | 小 | 高 — 立即节省 token，无新依赖 |
| **P0** | 8.2 Tool prompt() | 小 | 中 — 提升工具使用质量 |
| **P0** | 10.1 API 重试 | 小 | 中 — 提升稳定性 |
| **P1** | 7.1 use_skill Tool + loader | 中 | 高 — 复用已有 Skill 基础设施 |
| **P1** | 7.2 内置 Skills (6个) | 中 | 高 — 标准化排查流程 |
| **P1** | 6.1 单个子 Agent | 中 | 高 — 核心能力扩展 |
| **P1** | 6.2 并行假设验证 | 小 | 高 — 基于 6.1 |
| **P1** | 10.2 成本追踪 | 小 | 中 — 可观测性 |
| **P2** | 9 Hooks 系统 | 中 | 中 — 扩展性 |
| **P2** | 8.3 Memory 系统 | 大 | 中 — 需要 DB 迁移 |
| **P3** | 10.3 检索优化 | 中 | 低 — 等用户反馈 |

---

## 建议实施顺序

```
第一批（P0，快速收益）:
  8.1 Microcompact
  8.2 Tool prompt()
  10.1 API 重试
  ↓
第二批（P1，核心功能）:
  7.1 use_skill Tool
  7.2 内置 Skills
  6.1 单个子 Agent
  6.2 并行假设验证
  10.2 成本追踪
  ↓
第三批（P2，扩展能力）:
  9 Hooks 系统
  8.3 Memory 系统
  ↓
第四批（P3，按需）:
  10.3 检索优化
```

---

## 验证方案

每个 Phase 完成后：
1. 运行 `bun test` 确保所有单元测试通过
2. 现有 E2E 测试（agent-e2e, agent-search, agent-compact）不受影响
3. 新功能写对应的单元测试
4. 手动测试：创建一个模拟 incident，验证新功能端到端流程

---

## 需要更新的进度文档

完成后更新 `docs/ops-agent-progress.md`：
- Phase 5c 两项标记为 ✅（已完成）
- 对比表中 Embedding 缓存更新为 ✅
- 新增 Phase 6-10 的进度追踪
- 更新目录结构
