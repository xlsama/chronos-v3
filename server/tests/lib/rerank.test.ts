import { describe, it, expect, spyOn, beforeEach, afterEach } from "bun:test";
import { rerank } from "@/lib/rerank";

let fetchSpy: ReturnType<typeof spyOn>;

beforeEach(() => {
  fetchSpy = spyOn(globalThis, "fetch");
});

afterEach(() => {
  fetchSpy.mockRestore();
});

function mockFetchResponse(body: unknown, status = 200) {
  fetchSpy.mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("rerank", () => {
  describe("short-circuit cases", () => {
    it("returns empty array for empty documents", async () => {
      const result = await rerank("query", []);
      expect(result).toEqual([]);
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("returns all documents with score 1.0 when count < topN", async () => {
      const result = await rerank("query", ["doc1", "doc2"], { topN: 5 });
      expect(result).toEqual([
        { index: 0, relevanceScore: 1.0 },
        { index: 1, relevanceScore: 1.0 },
      ]);
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("returns all documents with score 1.0 when count equals topN", async () => {
      const result = await rerank("query", ["a", "b", "c"], { topN: 3 });
      expect(result).toEqual([
        { index: 0, relevanceScore: 1.0 },
        { index: 1, relevanceScore: 1.0 },
        { index: 2, relevanceScore: 1.0 },
      ]);
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });

  describe("API call behavior", () => {
    const docs = ["doc0", "doc1", "doc2", "doc3", "doc4", "doc5"];

    it("calls rerank API and returns filtered, sorted results", async () => {
      mockFetchResponse({
        results: [
          { index: 2, relevance_score: 0.95 },
          { index: 0, relevance_score: 0.5 },
          { index: 4, relevance_score: 0.05 },
        ],
      });

      const result = await rerank("error in nginx", docs, {
        topN: 3,
        scoreThreshold: 0.1,
      });

      // index 4 filtered out (score 0.05 < threshold 0.1), sorted descending
      expect(result).toEqual([
        { index: 2, relevanceScore: 0.95 },
        { index: 0, relevanceScore: 0.5 },
      ]);

      // Verify fetch was called with correct parameters
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const [url, options] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toContain("/reranks");
      expect(options.method).toBe("POST");

      const body = JSON.parse(options.body as string);
      expect(body.query).toBe("error in nginx");
      expect(body.documents).toEqual(docs);
      expect(body.top_n).toBe(3);
      expect(body.model).toBeDefined();
    });

    it("respects custom scoreThreshold", async () => {
      mockFetchResponse({
        results: [
          { index: 0, relevance_score: 0.9 },
          { index: 1, relevance_score: 0.4 },
          { index: 2, relevance_score: 0.2 },
        ],
      });

      const result = await rerank("query", docs, {
        topN: 3,
        scoreThreshold: 0.5,
      });

      expect(result).toEqual([{ index: 0, relevanceScore: 0.9 }]);
    });

    it("uses default topN=5", async () => {
      mockFetchResponse({
        results: [
          { index: 0, relevance_score: 0.8 },
        ],
      });

      await rerank("query", docs);

      const body = JSON.parse(
        (fetchSpy.mock.calls[0] as [string, RequestInit])[1].body as string,
      );
      expect(body.top_n).toBe(5);
    });

    it("throws on API error after retries exhausted", async () => {
      // p-retry retries 2 times, so 3 total attempts
      for (let i = 0; i < 3; i++) {
        fetchSpy.mockResolvedValueOnce(
          new Response("rate limited", { status: 429 }),
        );
      }

      await expect(rerank("query", docs)).rejects.toThrow(
        "Rerank API error (429)",
      );
      expect(fetchSpy).toHaveBeenCalledTimes(3);
    });

    it("succeeds on retry after transient failure", async () => {
      fetchSpy.mockResolvedValueOnce(
        new Response("server error", { status: 500 }),
      );
      mockFetchResponse({
        results: [{ index: 0, relevance_score: 0.9 }],
      });

      const result = await rerank("query", docs, { topN: 3 });
      expect(result).toEqual([{ index: 0, relevanceScore: 0.9 }]);
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it("throws on invalid response shape", async () => {
      mockFetchResponse({ unexpected: "shape" });

      await expect(rerank("query", docs)).rejects.toThrow();
    });
  });
});
