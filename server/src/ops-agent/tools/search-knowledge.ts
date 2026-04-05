import { z } from "zod";
import { db } from "../../db/connection";
import { hybridSearch } from "../../lib/hybrid-search";
import type { ToolDefinition } from "../types";

const schema = z.object({
  query: z.string().describe("搜索关键词或问题描述"),
  projectId: z.string().optional().describe("限定项目 ID，不传则搜索所有项目"),
});

type SearchKnowledgeArgs = z.infer<typeof schema>;

export const searchKnowledgeTool: ToolDefinition<SearchKnowledgeArgs> = {
  name: "search_knowledge",
  description: `搜索项目知识库文档。支持语义搜索和全文搜索混合检索。
使用场景：
- 排查前了解系统架构和配置
- 查找常见问题的解决方案
- 了解项目的运维规范和注意事项`,
  parameters: schema,
  needsPermissionCheck: false,
  maxResultChars: 15_000,

  async execute(args) {
    const results = await hybridSearch({
      query: args.query,
      table: "document_chunks",
      projectId: args.projectId,
      finalTopK: 5,
    });

    if (results.length === 0) {
      return "未找到相关知识库文档。";
    }

    // 获取关联的项目和文档信息
    const enriched = await Promise.all(
      results.map(async (r) => {
        let projectName = "";
        let docFilename = "";

        // 从 document_chunks 关联查询项目名和文档名
        try {
          const chunk = await db.execute(
            // biome-ignore lint: raw sql
            `SELECT dc.project_id, pd.filename, p.name as project_name
             FROM document_chunks dc
             JOIN project_documents pd ON dc.document_id = pd.id
             JOIN projects p ON dc.project_id = p.id
             WHERE dc.id = '${r.id}'
             LIMIT 1`,
          );
          const row = (chunk as unknown as Array<Record<string, string>>)[0];
          if (row) {
            projectName = row.project_name || "";
            docFilename = row.filename || "";
          }
        } catch {
          // ignore
        }

        return {
          project: projectName,
          document: docFilename,
          content: r.content.slice(0, 2000),
          score: Math.round(r.score * 100) / 100,
          source: r.source,
        };
      }),
    );

    return JSON.stringify(enriched, null, 2);
  },
};
