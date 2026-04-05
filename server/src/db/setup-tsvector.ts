/**
 * 为混合检索添加 tsvector 生成列和 GIN 索引。
 * 运行一次即可：bun run src/db/setup-tsvector.ts
 *
 * Drizzle 不支持 GENERATED ALWAYS AS STORED 列，所以用 raw SQL。
 * 使用 'simple' 配置（不做词干提取），对中文更友好。
 */

import { db } from "./connection";
import { sql } from "drizzle-orm";
import { logger } from "../lib/logger";

async function setupTsvector() {
  logger.info("[SETUP] Adding tsvector columns and GIN indexes...");

  // document_chunks.tsv
  await db.execute(sql`
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'document_chunks' AND column_name = 'tsv'
      ) THEN
        ALTER TABLE document_chunks
          ADD COLUMN tsv tsvector
          GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
      END IF;
    END $$
  `);

  await db.execute(sql`
    CREATE INDEX IF NOT EXISTS ix_document_chunks_tsv
      ON document_chunks USING GIN(tsv)
  `);

  // incident_history.tsv
  await db.execute(sql`
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'incident_history' AND column_name = 'tsv'
      ) THEN
        ALTER TABLE incident_history
          ADD COLUMN tsv tsvector
          GENERATED ALWAYS AS (to_tsvector('simple', title || ' ' || summary_md)) STORED;
      END IF;
    END $$
  `);

  await db.execute(sql`
    CREATE INDEX IF NOT EXISTS ix_incident_history_tsv
      ON incident_history USING GIN(tsv)
  `);

  // 同时确保向量列有 HNSW 索引
  await db.execute(sql`
    CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding
      ON document_chunks USING hnsw(embedding vector_cosine_ops)
  `);

  await db.execute(sql`
    CREATE INDEX IF NOT EXISTS ix_incident_history_embedding
      ON incident_history USING hnsw(embedding vector_cosine_ops)
  `);

  logger.info("[SETUP] tsvector setup complete.");
}

setupTsvector()
  .then(() => process.exit(0))
  .catch((err) => {
    logger.error(err, "[SETUP] Failed");
    process.exit(1);
  });
