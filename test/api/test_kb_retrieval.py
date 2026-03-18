"""Test KB vector retrieval + reranking raw results.

Usage:
    cd server && uv run python ../test/api/test_kb_retrieval.py -q "数据库超时" -p "<project_uuid>"
"""

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from bootstrap import get_embedder, get_reranker, get_session, print_divider, run_async


async def main(query: str, project_id: str):
    from src.db.vector_store import VectorStore

    embedder = get_embedder()
    reranker = get_reranker()

    # Step 1: Embed query
    print_divider("Step 1: Embedding")
    embedding = await embedder.embed_text(query)
    print(f"Query: {query}")
    print(f"Embedding dim: {len(embedding)}")

    # Step 2: Vector search
    print_divider("Step 2: Vector Search (top 20)")
    async with get_session() as session:
        vs = VectorStore(session)
        results = await vs.search(embedding, uuid.UUID(project_id), limit=20)

    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results):
        print(f"\n--- [{i + 1}] distance={r['distance']:.4f} | {r['filename']} (chunk #{r['chunk_index']})")
        print(r["content"][:300])
        if len(r["content"]) > 300:
            print(f"  ... ({len(r['content'])} chars)")

    # Step 3: Rerank
    print_divider(f"Step 3: Rerank (top 5 from {len(results)})")
    documents = [r["content"] for r in results]
    reranked = await reranker.rerank(query, documents, top_n=5)

    for rr in reranked:
        r = results[rr.index]
        print(f"\n--- [{rr.index + 1}] relevance={rr.relevance_score:.4f} | distance={r['distance']:.4f} | {r['filename']}")
        print(r["content"][:300])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test KB vector retrieval + reranking")
    parser.add_argument("-q", "--query", type=str, help="Search query")
    parser.add_argument("-p", "--project-id", type=str, required=True, help="Project UUID")
    args = parser.parse_args()

    query = args.query or input("Enter query: ").strip()
    if not query:
        print("Query is required.")
        sys.exit(1)

    run_async(main(query, args.project_id))
