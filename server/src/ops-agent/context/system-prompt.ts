import { db } from "../../db/connection";
import { servers, services } from "../../db/schema";
import type { AgentSession } from "../types";

export async function getSystemPrompt(session: AgentSession): Promise<string> {
  const parts: string[] = [BASE_PROMPT];

  // 自动注入可用资源
  const resources = await getAvailableResources();
  if (resources) {
    parts.push(resources);
  }

  if (session.planMd) {
    parts.push(`\n## 当前调查计划\n\n${session.planMd}`);
  }

  if (session.compactMd) {
    parts.push(`\n## 历史排查摘要\n\n${session.compactMd}`);
  }

  return parts.join("\n");
}

async function getAvailableResources(): Promise<string | null> {
  const allServers = await db.select().from(servers);
  const allServices = await db.select().from(services);

  if (allServers.length === 0 && allServices.length === 0) {
    return null;
  }

  const lines: string[] = ["\n## 可用资源\n"];

  if (allServers.length > 0) {
    lines.push("### Servers (SSH)");
    for (const s of allServers) {
      lines.push(`- ${s.name} (${s.host}:${s.port}) [ID: ${s.id}]`);
    }
    lines.push("");
  }

  if (allServices.length > 0) {
    lines.push("### Services");
    for (const s of allServices) {
      lines.push(`- ${s.name} (${s.serviceType}, ${s.host}:${s.port}) [ID: ${s.id}]`);
    }
    lines.push("");
  }

  lines.push(
    "使用 service_exec 时，请直接传入上面列出的 Service ID。",
  );

  return lines.join("\n");
}

const BASE_PROMPT = `你是一个专业的运维 Ops AI Agent。你的职责是帮助用户排查和解决运维问题。

## 工作流程

1. 先用 search_knowledge 搜索项目知识库，了解系统架构和配置
2. 用 search_incidents 搜索历史类似事件，参考之前的排查经验
3. 收集足够信息后，用 update_plan 制定调查计划
4. 按计划使用 service_exec 逐步排查，发现新线索时用 update_plan 更新计划
5. 如果信息不足，使用 ask_user_question 向用户提问
6. 完成后输出清晰的总结，不要再调用任何工具

## 工具使用原则

- search_knowledge: 排查前先搜索项目知识库，了解系统架构、配置和常见问题解决方案
- search_incidents: 搜索历史类似事件，参考之前的排查经验。相同症状可能有不同根因
- update_plan: 收集信息后制定调查计划（含假设和验证步骤），排查中发现新线索时更新计划
- service_exec: 执行 Docker/K8s/DB 等操作。使用下方"可用资源"中列出的 Service ID。优先使用此工具
- bash: 在本地执行 Shell 命令，用于 service_exec 无法覆盖的场景（文件检查、进程排查、网络诊断等）
- ask_user_question: 信息不足时向用户提问。不要反复追问，一次尽量问清楚
- 写操作（restart/stop/scale 等）需要审批，危险操作（delete/rm/kill/DROP 等）需要高级审批
- bash 中的危险命令（rm -rf、kill -9 等）同样会触发审批，灾难性命令（rm -rf /）会被直接拒绝
- 先用只读操作（list/inspect/logs/describe/ls/cat/ps）收集证据，再考虑写操作

## 输出格式

- 排查过程中保持简洁，重点说发现了什么
- 最终总结用 Markdown 格式，包含：问题描述、排查过程、根因分析、解决方案`;
