import type { ToolDefinition } from "../types";
import { serviceExecTool } from "./service-exec";
import { askUserQuestionTool } from "./ask-user-question";

// MVP: 只注册核心 2 个 Tool
// Phase 1+: list_servers, list_services, search_knowledge, search_incidents
// Phase 2+: update_plan, ssh_bash, bash

const ALL_TOOLS: ToolDefinition[] = [
  serviceExecTool as ToolDefinition,
  askUserQuestionTool as ToolDefinition,
];

export function buildToolRegistry(): ToolDefinition[] {
  return ALL_TOOLS;
}

export function getToolByName(name: string): ToolDefinition | undefined {
  return ALL_TOOLS.find((t) => t.name === name);
}
