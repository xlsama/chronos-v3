import { z } from "zod";
import type { ToolDefinition } from "../types";

const schema = z.object({
  planMd: z.string().describe("Markdown 格式的调查计划"),
  intent: z
    .enum(["incident", "question", "task"])
    .optional()
    .describe("事件意图分类（首次创建时填写）"),
});

type UpdatePlanArgs = z.infer<typeof schema>;

export const updatePlanTool: ToolDefinition<UpdatePlanArgs> = {
  name: "update_plan",
  description: `创建或更新调查计划。首次调用为创建，后续调用为更新。
调查计划应包含：
- 事件意图分类（incident/question/task）
- 假设列表（H1, H2, H3...）
- 每个假设的验证步骤和所需工具
- 标注哪些假设可以优先验证`,
  parameters: schema,
  needsPermissionCheck: false,
  maxResultChars: 1000,

  async execute() {
    // 实际的存储由 agent-loop.ts 中的特殊处理完成
    // （tc.name === "update_plan" 时 session.planMd = tc.args.planMd）
    return "计划已更新。";
  },
};
