# Chronos V3 Ops AI Agent — 进度对比与待办事项

> 更新时间：2026-04-05
> 对比对象：Claude Code / OpenHands / Dify

---

## 一、完成进度

### MVP ✅
- [x] `while(true)` + messages JSONB 驱动
- [x] async generator SSE 流
- [x] 双写持久化（agentMessages JSONB + messages 行表）
- [x] 9 个关键节点 `[AGENT]` 大写日志
- [x] maxTurns = 40 防死循环
- [x] `service_exec` Tool — 核心工具，路由到 Executor
- [x] `ask_user_question` Tool — 用户提问 + 中断
- [x] Docker Executor（21 个操作，dockerode）
- [x] Kubernetes Executor（12 个操作，@kubernetes/client-node）
- [x] 危险词判断（delete/remove/kill/restart…）→ ask 审批
- [x] 三种 resume：approval / human_input / confirm
- [x] approval_requests 表记录审批
- [x] agent_sessions 表（JSONB + 中断恢复字段）
- [x] AgentEventPublisher（8 个核心事件）
- [x] API 路由（run + resume SSE 端点）
- [x] E2E 测试：Docker 容器检查

### Phase 1: 上下文自动注入 + SQL/MongoDB ✅
- [x] System Prompt 自动注入 servers/services 列表（async DB 查询）
- [x] agent-loop 适配 async getSystemPrompt
- [x] SQL Executor（bun:sql，MySQL + PostgreSQL）
- [x] MongoDB Executor（官方驱动，8 个操作）
- [x] Executor Registry 注册 5 种 service type
- [x] messages 行表 role 语义修复（eventTypeToRole）

### Phase 2: 混合检索 + Plan ✅
- [x] tsvector 生成列 + GIN 索引（document_chunks + incident_history）
- [x] HNSW 向量索引
- [x] `hybrid-search.ts` 混合检索（向量 0.7 + 全文 0.3 + 融合 + rerank）
- [x] `update_plan` Tool — 创建/更新调查计划
- [x] `search_knowledge` Tool — 知识库混合检索
- [x] `search_incidents` Tool — 历史事件混合检索
- [x] Tool Registry 注册 5 个 Tool
- [x] System Prompt 增强（6 步工作流）
- [x] E2E 测试：知识库检索 + Docker 排查
- [x] E2E 测试：历史事件 + 排查

### Phase 3: 状态机加固 + Compact ✅
- [x] TerminalReason 类型（completed/failed/max_turns/interrupted/context_too_long）
- [x] 主动 compact 检查（shouldCompact，80K 字符阈值）
- [x] compact 核心实现（mini_model 5 段结构化摘要）
- [x] compact 后消息重建（rebuildAfterCompact：摘要 + 计划 + 原始问题）
- [x] 被动 compact（catch context_length_exceeded → compact → continue 重试）
- [x] Circuit breaker（MAX_COMPACT_FAILURES = 3）
- [x] compact_done 事件 + 双写持久化
- [x] E2E 测试：32→3 消息压缩 + 继续排查

---

## 二、待办事项

### Phase 4: Safety Classifier + Bash Tool ✅
- [x] `safety/permissions.ts` — CommandType → PermissionResult 共享映射（read→allow, write→ask MEDIUM, dangerous→ask HIGH, blocked→deny）
- [x] `safety/service-classifier.ts` — 按 service type + operation 静态分类（Docker 19 ops, K8s 11 ops, MongoDB 8 ops）+ executeSql SQL 正则
- [x] `safety/shell-classifier.ts` — 正则白名单/黑名单，四级分类（BLOCKED→DANGEROUS→WRITE→READ→默认 write）
- [x] `tools/bash.ts` — 本地 Shell 命令执行（Bun.spawn，超时控制，stdout+stderr 捕获）
- [x] 替换 `tools/service-exec.ts` 危险词判断为 ServiceSafety（查 DB 获取 serviceType → 分类器 → toPermissionResult）
- [x] 单元测试 — service-classifier（78 个）+ shell-classifier（127 个），共 205 个测试通过
- 设计决策：去掉 SSH Tool（Agent 认知负担大、生产环境少有 SSH 权限、安全风险高）

### Phase 5: 优化项（按需）

- [ ] **5.1 Tool 并发执行** — partitionToolCalls：只读工具并发，写操作串行
  - 参考：Claude Code `toolOrchestration.ts`

- [ ] **5.2 Embedding 缓存** — 按 hash 缓存到 DB，避免重复调用 embedding API
  - 参考：Dify `CacheEmbedding`

- [ ] **5.3 中文分词检索** — 加 JIEBA 分词 + BM25 评分（补充 tsvector simple 的不足）
  - 参考：Dify keyword search

- [ ] **5.4 incidents.summaryTitle 同步** — Agent 完成时同步更新 incident 标题

- [ ] **5.5 Token 精确估算** — 用 `roughTokenCountEstimation(content, bytesPerToken)` 替代纯字符数
  - 按内容类型区分：中文 bytesPerToken=2，英文=4，JSON=2
  - 参考：Claude Code `tokenEstimation.ts`

- [ ] **5.6 Prompt 缓存分层** — 静态部分（不变）+ 动态部分（每轮变化），提高 API 缓存命中率
  - 参考：Claude Code `DYNAMIC_BOUNDARY`

- [ ] **5.7 大结果磁盘持久化** — 工具输出超大时存磁盘，消息中只保留预览
  - 参考：Claude Code `toolResultStorage`

- [ ] **5.8 Token budget 控制** — 预算内执行，超预算暂停或总结
  - 参考：Claude Code `budgetTracker`

### Phase 6: 子 Agent（远期）

- [ ] **6.1 AgentTool** — 主 Agent 可 fork 子 Agent 执行特定假设的排查
  - 参考：Claude Code `AgentTool`

- [ ] **6.2 子 Agent 消息隔离** — 独立 messages 上下文 + agentId 分流
  - 参考：Claude Code `runAgent.ts`

- [ ] **6.3 并行子 Agent** — 多假设并行验证
  - 参考：Claude Code fork subagent

- [ ] **6.4 Verification Agent** — 只读验证 Agent，确认修复是否生效
  - 参考：原 Python 版 `verification_agent`

---

## 三、对比分析

### 1. 状态机设计

| 维度 | Claude Code | OpenHands | Chronos | 状态 |
|------|-------------|-----------|---------|------|
| 核心模式 | while(true) async generator | 事件溯源 EventLog | while(true) async generator | ✅ |
| 状态存储 | 内存 messages（进程存活） | ConversationState | messages JSONB（每轮持久化） | ✅ |
| 状态转换 | 7 个隐式 continue 点 | Action→Observation→EventLog | toolCalls if/switch 路由 | ✅ |
| 终止条件 | 12 种 return reason | AgentFinishAction | 5 种 TerminalReason | ✅ Phase 3 已补 |
| 错误恢复 | PTL→compact→collapse→重试 | 调整限制后恢复 | context_length→compact→重试 | ✅ Phase 3 已补 |
| 轮次控制 | maxTurns + token budget | max_iterations | maxTurns = 40 | ⚠️ 缺 token budget |

### 2. Tool 设计

| 维度 | Claude Code | OpenHands | Chronos | 状态 |
|------|-------------|-----------|---------|------|
| 数量 | 40+ | 核心 5 | 6（+bash） | ✅ |
| 权限检查 | 规则匹配 + AI 分类器 | Safety annotations + LLM 预测 | ServiceSafety + ShellSafety 分类器 | ✅ Phase 4 已补 |
| 并发执行 | 只读并发 + 写串行 | 单步顺序 | 顺序执行 | ⚠️ Phase 5 优化 |
| 输出控制 | 磁盘持久化 + 跨轮预算 | 无 | truncateOutput 截断 | ⚠️ Phase 5 优化 |

### 3. 子 Agent / 调度

| 维度 | Claude Code | OpenHands | Chronos | 状态 |
|------|-------------|-----------|---------|------|
| 子 Agent | AgentTool fork | DelegateTool 递归 | ❌ 无 | ❌ Phase 6 |
| 并行子 Agent | fork + background | ThreadPool | N/A | ❌ Phase 6 |

### 4. Compact / 上下文压缩

| 维度 | Claude Code | OpenHands | Chronos | 状态 |
|------|-------------|-----------|---------|------|
| 实现 | 4 层（snip→micro→collapse→auto） | LLMSummarizingCondenser | 1 层（字符数阈值 + mini_model） | ✅ Phase 3 已补 |
| 触发条件 | token 接近上限 - 13K buffer | 事件数超阈值 | 字符数 > 80K | ✅ |
| POST_COMPACT 恢复 | 文件+计划+技能+工具 delta | 保留初始 N 条 | 摘要+计划+原始问题 | ✅ |
| Circuit breaker | 连续 3 次失败停止 | 无 | 连续 3 次失败停止 | ✅ |

### 5. 提示词设计

| 维度 | Claude Code | OpenHands | Chronos | 状态 |
|------|-------------|-----------|---------|------|
| 结构分层 | 静态（缓存）+ 动态（每轮） | Agent prompt + 事件历史 | BASE_PROMPT + 资源 + 计划 + compact | ⚠️ Phase 5 优化 |
| 工具指导 | 每 Tool 独立 prompt() | Action docstring | 静态 description | ⚠️ |
| 动态注入 | Attachment 机制 | EventLog 自然积累 | system prompt 注入 | ✅ 当前够用 |

### 6. 知识库检索（对比 Dify）

| 维度 | Dify | Chronos | 状态 |
|------|------|---------|------|
| 混合检索 | 向量+全文+关键词+混合 | 向量+全文混合 | ✅ |
| Rerank | 模型 rerank + 加权融合 | 模型 rerank | ✅ |
| Embedding 缓存 | hash → DB 缓存 | ❌ 无 | ⚠️ Phase 5 优化 |
| 中文分词 | JIEBA + BM25 | tsvector simple | ⚠️ Phase 5 优化 |

---

## 四、设计注意点（实现时参考）

1. **incidents.summaryTitle 同步** — Agent 完成时同步更新 incident 标题，可直接截取 summary 前 100 字
2. **pendingApprovalId 无外键** — 故意不加外键到 approval_requests，应用层保证一致性
3. **Agent 状态 vs Incident 状态独立** — agent done ≠ incident resolved，需用户确认
4. **agentMessages 体积控制** — compact 后旧历史可存入 content_versions 归档
5. **service_exec operation 命名** — 各 Executor 保持 camelCase，System Prompt 中列出支持的操作清单
6. **Token 估算精度** — 中文约 1-2 字符/token，英文约 4 字符/token，JSON 约 2 字符/token。Phase 3 用字符数阈值 80K，Phase 5 可加 roughTokenCountEstimation

---

## 五、当前目录结构

```
server/src/ops-agent/
├── index.ts                    # 公共 API
├── types.ts                    # 所有类型定义 + TerminalReason
├── agent-loop.ts               # runAgent（while true + compact + 错误恢复）
├── resume.ts                   # resumeAgent（3 种恢复）
├── session.ts                  # 双写持久化 + createApproval
├── tools/
│   ├── registry.ts             # 6 个 Tool 注册
│   ├── service-exec.ts         # service_exec（核心，ServiceSafety 权限检查）
│   ├── bash.ts                 # bash（本地命令执行，ShellSafety 权限检查）
│   ├── ask-user-question.ts    # ask_user_question
│   ├── update-plan.ts          # update_plan
│   ├── search-knowledge.ts     # search_knowledge（混合检索）
│   └── search-incidents.ts     # search_incidents（混合检索）
├── executors/
│   ├── registry.ts             # 5 种 service type 路由 + destr 参数解析
│   ├── docker.ts               # Docker（21 ops）
│   ├── kubernetes.ts           # K8s（12 ops，支持 skipTLSVerify）
│   ├── sql.ts                  # PostgreSQL（bun:sql）
│   ├── mysql.ts                # MySQL（bun:sql）
│   └── mongodb.ts              # MongoDB（8 ops）
├── context/
│   ├── system-prompt.ts        # getSystemPrompt（async，自动注入资源）
│   ├── compact.ts              # shouldCompact + compactMessages + rebuildAfterCompact
│   ├── compact-prompts.ts      # COMPACT_SYSTEM_PROMPT
│   └── truncation.ts           # truncateOutput
├── events/
│   └── publisher.ts            # AgentEventPublisher（含 compactDone）
├── safety/
│   ├── permissions.ts          # toPermissionResult（CommandType → PermissionResult）
│   ├── service-classifier.ts   # classifyServiceOperation（静态映射 + SQL 正则）
│   └── shell-classifier.ts     # classifyShellCommand（正则白名单/黑名单）

server/src/lib/
├── hybrid-search.ts            # 混合检索（向量+全文+融合+rerank）
├── embedder.ts                 # embedTexts（DashScope）
└── rerank.ts                   # rerank（qwen3-rerank）

server/src/db/
├── schema.ts                   # 所有表定义（含 agentSessions）
├── connection.ts               # DB 连接
└── setup-tsvector.ts           # tsvector 生成列 + GIN/HNSW 索引

server/tests/ops-agent/
├── agent-e2e.test.ts           # MVP: Docker 容器检查
├── agent-search.test.ts        # Phase 2: 知识库 + 历史事件（2 个场景）
├── agent-compact.test.ts       # Phase 3: Compact 触发 + 恢复
├── service-classifier.test.ts  # Phase 4: ServiceSafety 单元测试（78 个）
└── shell-classifier.test.ts    # Phase 4: ShellSafety 单元测试（127 个）
```
