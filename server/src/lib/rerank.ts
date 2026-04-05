import { z } from "zod";
import pRetry from "p-retry";
import { env } from "@/env";

export interface RerankResult {
  index: number;
  relevanceScore: number;
}

export interface RerankOptions {
  topN?: number;
  scoreThreshold?: number;
}

const rerankResponseSchema = z.object({
  results: z.array(
    z.object({
      index: z.number(),
      relevance_score: z.number(),
    }),
  ),
});

export async function rerank(
  query: string,
  documents: string[],
  options?: RerankOptions,
): Promise<RerankResult[]> {
  const topN = options?.topN ?? 5;
  const scoreThreshold = options?.scoreThreshold ?? 0.1;

  if (!documents.length || documents.length <= topN) {
    return documents.map((_, i) => ({ index: i, relevanceScore: 1.0 }));
  }

  const response = await pRetry(
    async () => {
      const res = await fetch(`${env.RERANK_BASE_URL}/reranks`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.DASHSCOPE_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: env.RERANK_MODEL,
          query,
          documents,
          top_n: topN,
        }),
        signal: AbortSignal.timeout(30_000),
      });

      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`Rerank API error (${res.status}): ${text}`);
      }

      return res;
    },
    { retries: env.API_RETRIES },
  );

  const data = rerankResponseSchema.parse(await response.json());

  return data.results
    .filter((r) => r.relevance_score >= scoreThreshold)
    .map((r) => ({ index: r.index, relevanceScore: r.relevance_score }))
    .sort((a, b) => b.relevanceScore - a.relevanceScore);
}
