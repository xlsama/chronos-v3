import { describe, it, expect } from "bun:test";
import { chunkText, chunkSegments } from "@/lib/chunker";
import type { ParsedSegment } from "@/lib/chunker";

describe("chunkText", () => {
  it("returns empty array for empty/blank text", () => {
    expect(chunkText("")).toEqual([]);
    expect(chunkText("   ")).toEqual([]);
    expect(chunkText("\n\n")).toEqual([]);
  });

  it("returns single chunk for short text", () => {
    expect(chunkText("Hello world")).toEqual(["Hello world"]);
  });

  it("splits by double newlines", () => {
    const text = "Paragraph one.\n\nParagraph two.\n\nParagraph three.";
    const chunks = chunkText(text, 500);
    expect(chunks).toEqual([
      "Paragraph one.",
      "Paragraph two.",
      "Paragraph three.",
    ]);
  });

  it("splits by markdown headers", () => {
    const text = "# Title\nSome text\n## Subtitle\nMore text";
    const chunks = chunkText(text, 500);
    expect(chunks).toEqual(["# Title\nSome text", "## Subtitle\nMore text"]);
  });

  it("splits long segments by lines", () => {
    const line1 = "a".repeat(300);
    const line2 = "b".repeat(300);
    const text = `${line1}\n${line2}`;
    const chunks = chunkText(text, 500);
    expect(chunks).toEqual([line1, line2]);
  });

  it("truncates single lines exceeding maxChars", () => {
    const longLine = "x".repeat(1000);
    const chunks = chunkText(longLine, 500);
    expect(chunks.length).toBe(1);
    expect(chunks[0].length).toBe(500);
  });

  it("accumulates short lines into one chunk", () => {
    const lines = Array.from({ length: 5 }, (_, i) => `Line ${i + 1}`);
    const text = lines.join("\n");
    const chunks = chunkText(text, 500);
    expect(chunks).toEqual([text]);
  });

  it("respects custom maxChars", () => {
    const text = "Part A content.\n\nPart B content.";
    const chunks = chunkText(text, 10);
    expect(chunks.length).toBe(2);
    for (const chunk of chunks) {
      expect(chunk.length).toBeLessThanOrEqual(15); // "Part A content." is 15 chars
    }
  });
});

describe("chunkSegments", () => {
  it("returns empty array for empty segments", () => {
    expect(chunkSegments([])).toEqual([]);
  });

  it("propagates metadata and assigns indices", () => {
    const segments: ParsedSegment[] = [
      { content: "Page one content.\n\nSecond paragraph.", metadata: { page: 1 } },
      { content: "Page two content.", metadata: { page: 2 } },
    ];
    const chunks = chunkSegments(segments, 500);

    expect(chunks.length).toBe(3);
    expect(chunks[0]).toEqual({
      content: "Page one content.",
      metadata: { page: 1 },
      index: 0,
    });
    expect(chunks[1]).toEqual({
      content: "Second paragraph.",
      metadata: { page: 1 },
      index: 1,
    });
    expect(chunks[2]).toEqual({
      content: "Page two content.",
      metadata: { page: 2 },
      index: 2,
    });
  });

  it("skips empty segments", () => {
    const segments: ParsedSegment[] = [
      { content: "", metadata: {} },
      { content: "Real content.", metadata: { page: 1 } },
    ];
    const chunks = chunkSegments(segments, 500);
    expect(chunks.length).toBe(1);
    expect(chunks[0].content).toBe("Real content.");
    expect(chunks[0].index).toBe(0);
  });
});
