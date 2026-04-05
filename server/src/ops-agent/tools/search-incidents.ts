import { z } from "zod";
import { hybridSearch } from "../../lib/hybrid-search";
import type { ToolDefinition } from "../types";

const schema = z.object({
  query: z.string().describe("搜索关键词或问题描述"),
});

type SearchIncidentsArgs = z.infer<typeof schema>;

export const searchIncidentsTool: ToolDefinition<SearchIncidentsArgs> = {
  name: "search_incidents",
  description: `搜索历史类似事件。支持语义搜索和全文搜索混合检索。
使用场景：
- 排查前查找类似的历史事件
- 参考之前的排查经验和解决方案
- 了解同类问题的发生频率和根因`,
  parameters: schema,
  needsPermissionCheck: false,
  maxResultChars: 10_000,

  async execute(args) {
    const results = await hybridSearch({
      query: args.query,
      table: "incident_history",
      finalTopK: 5,
    });

    if (results.length === 0) {
      return "未找到类似的历史事件。";
    }

    const formatted = results.map((r) => {
      const meta = r.metadata as Record<string, unknown>;
      return {
        title: meta.title || "未命名事件",
        summary: r.content.slice(0, 1500),
        occurrenceCount: meta.occurrenceCount || 1,
        lastSeenAt: meta.lastSeenAt || "",
        score: Math.round(r.score * 100) / 100,
      };
    });

    return JSON.stringify(formatted, null, 2);
  },
};
