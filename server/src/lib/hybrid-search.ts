import { db } from "@/db/connection";
import { sql } from "drizzle-orm";
import { logger } from "@/lib/logger";
import { embedTexts } from "@/lib/embedder";
import { rerank } from "@/lib/rerank";

export interface SearchResult {
  id: string;
  content: string;
  score: number;
  source: "vector" | "fulltext" | "both";
  metadata: Record<string, unknown>;
}

export interface HybridSearchOptions {
  query: string;
  table: "document_chunks" | "incident_history";
  limit?: number;
  finalTopK?: number;
  vectorWeight?: number;
  textWeight?: number;
  projectId?: string;
  useRerank?: boolean;
}

const DEFAULT_LIMIT = 20;
const DEFAULT_FINAL_TOP_K = 5;
const DEFAULT_VECTOR_WEIGHT = 0.7;
const DEFAULT_TEXT_WEIGHT = 0.3;

export async function hybridSearch(
  options: HybridSearchOptions,
): Promise<SearchResult[]> {
  const {
    query,
    table,
    limit = DEFAULT_LIMIT,
    finalTopK = DEFAULT_FINAL_TOP_K,
    vectorWeight = DEFAULT_VECTOR_WEIGHT,
    textWeight = DEFAULT_TEXT_WEIGHT,
    projectId,
    useRerank = true,
  } = options;

  logger.debug(`[SEARCH] hybrid query="${query.slice(0, 80)}", table=${table}, limit=${limit}`);

  // 1. 并行执行向量搜索和全文搜索
  const [vectorResults, fulltextResults] = await Promise.all([
    vectorSearch(query, table, limit, projectId),
    fulltextSearch(query, table, limit, projectId),
  ]);

  logger.debug(
    `[SEARCH] vector=${vectorResults.length} results, fulltext=${fulltextResults.length} results`,
  );

  // 2. 去重 + 加权融合
  const merged = mergeResults(vectorResults, fulltextResults, vectorWeight, textWeight);

  // 3. 按融合分数排序
  merged.sort((a, b) => b.score - a.score);

  // 4. rerank（可选）
  if (useRerank && merged.length > 0) {
    const contents = merged.map((r) => r.content);
    const rerankResults = await rerank(query, contents, {
      topN: finalTopK,
      scoreThreshold: 0.1,
    });

    const reranked = rerankResults.map((r) => ({
      ...merged[r.index],
      score: r.relevanceScore,
    }));

    logger.debug(`[SEARCH] reranked to ${reranked.length} results`);
    return reranked;
  }

  return merged.slice(0, finalTopK);
}

// ─── Vector Search ─────────────────────────────────────

interface RawSearchRow {
  id: string;
  content: string;
  score: number;
  metadata: Record<string, unknown>;
}

async function vectorSearch(
  query: string,
  table: string,
  limit: number,
  projectId?: string,
): Promise<SearchResult[]> {
  const [queryEmbedding] = await embedTexts([query]);
  const vectorStr = `[${queryEmbedding.join(",")}]`;

  let rows: RawSearchRow[];

  if (table === "document_chunks") {
    const projectFilter = projectId
      ? sql`AND project_id = ${projectId}`
      : sql``;

    rows = (await db.execute(sql`
      SELECT id, content, 1 - (embedding <=> ${vectorStr}::vector) as score,
             metadata::text as metadata_raw
      FROM document_chunks
      WHERE embedding IS NOT NULL ${projectFilter}
      ORDER BY embedding <=> ${vectorStr}::vector
      LIMIT ${limit}
    `)) as unknown as RawSearchRow[];
  } else {
    rows = (await db.execute(sql`
      SELECT id, summary_md as content, 1 - (embedding <=> ${vectorStr}::vector) as score,
             json_build_object('title', title, 'occurrenceCount', occurrence_count, 'lastSeenAt', last_seen_at)::text as metadata_raw
      FROM incident_history
      WHERE embedding IS NOT NULL
      ORDER BY embedding <=> ${vectorStr}::vector
      LIMIT ${limit}
    `)) as unknown as RawSearchRow[];
  }

  return rows.map((r) => ({
    id: r.id,
    content: r.content,
    score: Number(r.score),
    source: "vector" as const,
    metadata: parseMetadata(r as unknown as Record<string, unknown>),
  }));
}

// ─── Full-text Search ──────────────────────────────────

async function fulltextSearch(
  query: string,
  table: string,
  limit: number,
  projectId?: string,
): Promise<SearchResult[]> {
  let rows: RawSearchRow[];

  if (table === "document_chunks") {
    const projectFilter = projectId
      ? sql`AND project_id = ${projectId}`
      : sql``;

    rows = (await db.execute(sql`
      SELECT id, content, ts_rank(tsv, plainto_tsquery('simple', ${query})) as score,
             metadata::text as metadata_raw
      FROM document_chunks
      WHERE tsv @@ plainto_tsquery('simple', ${query}) ${projectFilter}
      ORDER BY score DESC
      LIMIT ${limit}
    `)) as unknown as RawSearchRow[];
  } else {
    rows = (await db.execute(sql`
      SELECT id, summary_md as content, ts_rank(tsv, plainto_tsquery('simple', ${query})) as score,
             json_build_object('title', title, 'occurrenceCount', occurrence_count, 'lastSeenAt', last_seen_at)::text as metadata_raw
      FROM incident_history
      WHERE tsv @@ plainto_tsquery('simple', ${query})
      ORDER BY score DESC
      LIMIT ${limit}
    `)) as unknown as RawSearchRow[];
  }

  return rows.map((r) => ({
    id: r.id,
    content: r.content,
    score: Number(r.score),
    source: "fulltext" as const,
    metadata: parseMetadata(r as unknown as Record<string, unknown>),
  }));
}

// ─── Merge & Deduplicate ───────────────────────────────

function mergeResults(
  vectorResults: SearchResult[],
  fulltextResults: SearchResult[],
  vectorWeight: number,
  textWeight: number,
): SearchResult[] {
  const map = new Map<string, SearchResult & { vectorScore: number; textScore: number }>();

  // Normalize vector scores to [0, 1]
  const maxVectorScore = Math.max(...vectorResults.map((r) => r.score), 0.001);
  for (const r of vectorResults) {
    map.set(r.id, {
      ...r,
      score: 0,
      source: "vector",
      vectorScore: r.score / maxVectorScore,
      textScore: 0,
    });
  }

  // Normalize fulltext scores to [0, 1]
  const maxTextScore = Math.max(...fulltextResults.map((r) => r.score), 0.001);
  for (const r of fulltextResults) {
    const existing = map.get(r.id);
    if (existing) {
      existing.textScore = r.score / maxTextScore;
      existing.source = "both";
    } else {
      map.set(r.id, {
        ...r,
        score: 0,
        source: "fulltext",
        vectorScore: 0,
        textScore: r.score / maxTextScore,
      });
    }
  }

  // Weighted fusion
  for (const entry of map.values()) {
    entry.score = vectorWeight * entry.vectorScore + textWeight * entry.textScore;
  }

  return [...map.values()];
}

// ─── Helpers ───────────────────────────────────────────

function parseMetadata(row: Record<string, unknown>): Record<string, unknown> {
  const raw = row.metadata_raw || row.metadata;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }
  return (raw as Record<string, unknown>) || {};
}
