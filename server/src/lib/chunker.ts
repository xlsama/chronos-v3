export interface ParsedSegment {
  content: string;
  metadata: Record<string, unknown>;
}

export interface Chunk {
  content: string;
  metadata: Record<string, unknown>;
  index: number;
}

/**
 * 对每个 segment 分块并传播其 metadata，最终统一分配递增 index。
 */
export function chunkSegments(
  segments: ParsedSegment[],
  maxChars = 500,
): Chunk[] {
  const result: Chunk[] = [];
  let index = 0;
  for (const seg of segments) {
    const texts = chunkText(seg.content, maxChars);
    for (const text of texts) {
      result.push({ content: text, metadata: seg.metadata, index: index++ });
    }
  }
  return result;
}

/**
 * 将文本按 markdown 标题 / 双换行 / 行 分块。
 */
export function chunkText(text: string, maxChars = 500): string[] {
  if (!text?.trim()) return [];

  // 按 markdown header 或双换行分割
  const segments = text.split(/\n(?=#{1,6}\s)|\n\n+/);
  const chunks: string[] = [];

  for (const raw of segments) {
    const segment = raw.trim();
    if (!segment) continue;

    if (segment.length <= maxChars) {
      chunks.push(segment);
    } else {
      splitLongSegment(segment, maxChars, chunks);
    }
  }

  return chunks;
}

function splitLongSegment(
  segment: string,
  maxChars: number,
  chunks: string[],
): void {
  const lines = segment.split("\n");
  let current = "";

  for (const line of lines) {
    const candidate = current ? `${current}\n${line}`.trim() : line;
    if (candidate.length <= maxChars) {
      current = candidate;
    } else {
      if (current) chunks.push(current);
      current = line.length > maxChars ? line.slice(0, maxChars) : line;
    }
  }

  if (current.trim()) {
    chunks.push(current);
  }
}
