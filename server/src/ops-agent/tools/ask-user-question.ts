import { z } from "zod";
import type { ToolDefinition } from "../types";

const schema = z.object({
  question: z.string().describe("向用户提出的问题"),
});

type AskUserQuestionArgs = z.infer<typeof schema>;

export const askUserQuestionTool: ToolDefinition<AskUserQuestionArgs> = {
  name: "ask_user_question",
  description: `向用户提问以获取更多信息。调用后 Agent 会暂停，等待用户回复。
仅在以下情况使用：
- 缺少关键信息无法继续排查
- 需要用户确认某个操作
- 需要用户提供截图中的具体内容`,
  parameters: schema,
  needsPermissionCheck: false,
  maxResultChars: 1000,

  async execute(args) {
    // 实际的中断逻辑由 agent-loop 处理
    // 这里只返回确认信息，会被追加到 messages 中
    return `已向用户提问: ${args.question}`;
  },
};
