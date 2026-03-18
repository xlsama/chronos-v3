"""历史事件向量检索 + Rerank 测试"""

import pytest

pytestmark = pytest.mark.api
QUERY = "服务器宕机"


@pytest.mark.asyncio
async def test_find_similar(embedder, db_session):
    """find_similar 返回 list[tuple]，无数据时返回空列表"""
    from src.services.incident_history_service import IncidentHistoryService

    embedding = await embedder.embed_text(QUERY)
    svc = IncidentHistoryService(db_session, embedder=embedder)
    results = await svc.find_similar(embedding, limit=20)
    print(f"find_similar returned {len(results)} results")
    for i, (record, distance) in enumerate(results):
        print(f"  [{i+1}] distance={distance:.4f} | {record.title}")
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_search_with_rerank(embedder, db_session):
    """search 返回 rerank 后的结果，无数据时返回空列表"""
    from src.services.incident_history_service import IncidentHistoryService

    svc = IncidentHistoryService(db_session, embedder=embedder)
    results = await svc.search(QUERY, limit=5)
    print(f"search returned {len(results)} results")
    for i, r in enumerate(results):
        print(f"  [{i+1}] relevance={r['relevance_score']:.4f} | {r['title']}")
    assert isinstance(results, list)
    assert len(results) <= 5
