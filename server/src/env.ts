import { z } from "zod";

const envSchema = z.object({
  // Database
  DATABASE_URL: z.string().default("postgresql://chronos:chronos@localhost:5432/chronos"),

  // Redis
  REDIS_URL: z.string().default("redis://localhost:6379/0"),

  // DashScope / Bailian
  DASHSCOPE_API_KEY: z.string().default(""),
  LLM_BASE_URL: z.string().default("https://dashscope.aliyuncs.com/compatible-mode/v1"),
  MAIN_MODEL: z.string().default("qwen3.6-plus"),
  MINI_MODEL: z.string().default("qwen3.5-flash"),
  EMBEDDING_MODEL: z.string().default("text-embedding-v4"),
  EMBEDDING_DIMENSION: z.coerce.number().default(1024),
  RERANK_MODEL: z.string().default("qwen3-rerank"),
  RERANK_BASE_URL: z.string().default("https://dashscope.aliyuncs.com/compatible-api/v1"),
  VISION_MODEL: z.string().default("qwen-vl-max"),

  // API
  API_RETRIES: z.coerce.number().default(2),

  // Agent
  AGENT_RECURSION_LIMIT: z.coerce.number().default(200),
  TOOL_CALL_MAX_RETRIES: z.coerce.number().default(2),
  COMMAND_TIMEOUT: z.coerce.number().default(10),

  // Cron
  SKILL_EVOLUTION_INTERVAL: z.coerce.number().default(8),

  // Data directories
  DATA_DIR: z.string().default("data"),
  SEEDS_DIR: z.string().default("seeds"),

  // Security
  ENCRYPTION_KEY: z.string().default("dGVzdC1lbmNyeXB0aW9uLWtleS0zMmJ5dGVz"),
  JWT_SECRET: z.string().default("024HX4wfCMjAQMsm9G3LVIhCFERo5G0-mR5s2KxBOqE"),
  JWT_EXPIRATION: z.string().default("0"),

  // Server
  PORT: z.coerce.number().default(8000),
  LOG_LEVEL: z.string().default("debug"),
});

export type Env = z.infer<typeof envSchema>;

export const env = envSchema.parse(process.env);
