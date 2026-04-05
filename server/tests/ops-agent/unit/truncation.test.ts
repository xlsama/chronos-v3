import { describe, it, expect } from "vitest";
import { truncateOutput } from "@/ops-agent/context/truncation";

describe("truncateOutput", () => {
  it("不超限时返回原文", () => {
    expect(truncateOutput("hello", 100)).toBe("hello");
  });

  it("恰好等于限制时返回原文", () => {
    const text = "x".repeat(100);
    expect(truncateOutput(text, 100)).toBe(text);
  });

  it("超限时截断为前半 + 标记 + 后半", () => {
    const text = "A".repeat(100) + "B".repeat(100);
    const result = truncateOutput(text, 100);
    expect(result.startsWith("A".repeat(50))).toBe(true);
    expect(result.endsWith("B".repeat(50))).toBe(true);
    expect(result).toContain("输出已截断");
  });

  it("截断标记包含原始长度", () => {
    const text = "x".repeat(200);
    const result = truncateOutput(text, 100);
    expect(result).toContain("原始长度 200 字符");
  });

  it("空字符串返回空字符串", () => {
    expect(truncateOutput("", 100)).toBe("");
  });

  it("maxChars=0 时截断任何非空输入", () => {
    const result = truncateOutput("hello", 0);
    expect(result).toContain("输出已截断");
  });
});
