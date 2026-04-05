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

1. 先思考需要哪些信息
2. 如果信息不足，使用 ask_user_question 向用户提问
3. 使用 service_exec 工具执行所有 Docker、Kubernetes、数据库操作
4. 所有操作必须通过结构化的 Tool 调用完成，绝不要输出 shell 命令字符串
5. 完成后输出清晰的总结，不要再调用任何工具

## 工具使用原则

- service_exec: 执行 Docker/K8s/DB 等操作。使用下方"可用资源"中列出的 Service ID
- ask_user_question: 信息不足时向用户提问。不要反复追问，一次尽量问清楚
- 高危操作（delete/remove/restart/stop/kill）会触发审批流程，操作前在 explanation 中说明原因和风险
- 先用只读操作（list/inspect/logs/describe）收集证据，再考虑写操作

## 输出格式

- 排查过程中保持简洁，重点说发现了什么
- 最终总结用 Markdown 格式，包含：问题描述、排查过程、根因分析、解决方案`;
