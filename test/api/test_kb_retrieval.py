"""KB 向量检索 + Rerank 测试"""

import uuid

import pytest

pytestmark = pytest.mark.api
QUERY = "数据库连接超时"


@pytest.mark.asyncio
async def test_embedding(embedder):
    """Embedder 能正常生成向量"""
    embedding = await embedder.embed_text(QUERY)
    print(f"Query: {QUERY}")
    print(f"Embedding dim: {len(embedding)}")
    assert len(embedding) > 0


@pytest.mark.asyncio
async def test_vector_search(embedder, db_session, project_id):
    """VectorStore.search 返回结果且格式正确"""
    from src.db.vector_store import VectorStore

    embedding = await embedder.embed_text(QUERY)
    vs = VectorStore(db_session)
    results = await vs.search(embedding, uuid.UUID(project_id), limit=20)
    print(f"Vector search returned {len(results)} results")
    for i, r in enumerate(results):
        print(f"  [{i+1}] distance={r['distance']:.4f} | {r['filename']} (chunk #{r['chunk_index']})")
    assert len(results) > 0
    assert "content" in results[0]
    assert "distance" in results[0]
    assert "filename" in results[0]


@pytest.mark.asyncio
async def test_rerank(embedder, reranker, db_session, project_id):
    """Reranker 能对搜索结果重排序，结果数 <= top_n"""
    from src.db.vector_store import VectorStore

    embedding = await embedder.embed_text(QUERY)
    vs = VectorStore(db_session)
    results = await vs.search(embedding, uuid.UUID(project_id), limit=20)
    documents = [r["content"] for r in results]
    reranked = await reranker.rerank(QUERY, documents, top_n=5)
    print(f"Reranked {len(results)} → {len(reranked)} results")
    for rr in reranked:
        r = results[rr.index]
        print(f"  [{rr.index+1}] relevance={rr.relevance_score:.4f} | {r['filename']}")
    assert len(reranked) <= 5
    assert all(rr.relevance_score >= 0 for rr in reranked)
