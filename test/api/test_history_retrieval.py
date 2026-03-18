"""Test incident history vector retrieval + reranking raw results.

Usage:
    cd server && uv run python ../test/api/test_history_retrieval.py -q "服务器宕机"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from bootstrap import get_embedder, get_session, print_divider, run_async


async def main(query: str):
    from src.services.incident_history_service import IncidentHistoryService

    embedder = get_embedder()

    # Step 1: Raw vector search via find_similar
    print_divider("Step 1: Vector Search (find_similar, top 20)")
    embedding = await embedder.embed_text(query)
    print(f"Query: {query}")
    print(f"Embedding dim: {len(embedding)}")

    async with get_session() as session:
        svc = IncidentHistoryService(session, embedder=embedder)

        similar = await svc.find_similar(embedding, limit=20)
        if not similar:
            print("No results found.")
        else:
            for i, (record, distance) in enumerate(similar):
                print(f"\n--- [{i + 1}] distance={distance:.4f} | {record.title}")
                text = record.summary_md or ""
                print(text[:500])
                if len(text) > 500:
                    print(f"  ... ({len(text)} chars)")

        # Step 2: Full search with reranking
        print_divider("Step 2: Search with Reranking (top 5)")
        results = await svc.search(query, limit=5)

        if not results:
            print("No results found.")
        else:
            for i, r in enumerate(results):
                print(f"\n--- [{i + 1}] relevance={r['relevance_score']:.4f} | distance={r['distance']:.4f} | {r['title']}")
                text = r["summary_md"] or ""
                print(text[:500])
                if len(text) > 500:
                    print(f"  ... ({len(text)} chars)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test incident history retrieval + reranking")
    parser.add_argument("-q", "--query", type=str, help="Search query")
    args = parser.parse_args()

    query = args.query or input("Enter query: ").strip()
    if not query:
        print("Query is required.")
        sys.exit(1)

    run_async(main(query))
