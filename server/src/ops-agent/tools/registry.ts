import type { ToolDefinition } from "../types";
import { serviceExecTool } from "./service-exec";
import { bashTool } from "./bash";
import { askUserQuestionTool } from "./ask-user-question";
import { updatePlanTool } from "./update-plan";
import { searchKnowledgeTool } from "./search-knowledge";
import { searchIncidentsTool } from "./search-incidents";

const ALL_TOOLS: ToolDefinition[] = [
  serviceExecTool as ToolDefinition,
  bashTool as ToolDefinition,
  askUserQuestionTool as ToolDefinition,
  updatePlanTool as ToolDefinition,
  searchKnowledgeTool as ToolDefinition,
  searchIncidentsTool as ToolDefinition,
];

export function buildToolRegistry(): ToolDefinition[] {
  return ALL_TOOLS;
}

export function getToolByName(name: string): ToolDefinition | undefined {
  return ALL_TOOLS.find((t) => t.name === name);
}
