import { createOpenAI } from "@ai-sdk/openai";
import { embedMany } from "ai";
import { env } from "@/env";

const dashscope = createOpenAI({
  apiKey: env.DASHSCOPE_API_KEY,
  baseURL: env.LLM_BASE_URL,
});

export async function embedTexts(texts: string[]): Promise<number[][]> {
  if (!texts.length) return [];

  const { embeddings } = await embedMany({
    model: dashscope.embeddingModel(env.EMBEDDING_MODEL),
    values: texts,
    providerOptions: {
      openai: { dimensions: env.EMBEDDING_DIMENSION },
    },
  });

  return embeddings;
}
