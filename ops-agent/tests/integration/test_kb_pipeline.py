"""Knowledge base full-pipeline integration tests.

Requires: DASHSCOPE_API_KEY + PostgreSQL with pgvector.
Run with: uv run pytest -m integration -v
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from src.db.vector_store import VectorStore
from src.services.document_service import DocumentService
from src.tools.knowledge_tools import _format_source, search_knowledge_base

from .helpers import (
    create_test_csv,
    create_test_docx,
    create_test_excel,
    create_test_image,
    create_test_pdf,
    create_test_pptx,
)

pytestmark = pytest.mark.integration


# ── 4.1 Text: upload → store → vector search ──


async def test_text_upload_and_search(db_session, real_embedder, test_project):
    """Upload markdown, embed, and search with vector similarity."""
    service = DocumentService(session=db_session, embedder=real_embedder)

    content = (
        "# Nginx 负载均衡配置\n\n"
        "upstream backend {\n"
        "    server 10.0.0.1:8080 weight=3;\n"
        "    server 10.0.0.2:8080 weight=2;\n"
        "}\n\n"
        "使用 round-robin 算法进行请求分发，支持权重配置。"
    )

    doc = await service.upload(
        project_id=test_project.id,
        filename="nginx-lb.md",
        content=content,
        doc_type="markdown",
    )
    assert doc.status == "ready"

    # Search
    query_embedding = await real_embedder.embed_text("nginx 负载均衡")
    store = VectorStore(session=db_session)
    results = await store.search(query_embedding, test_project.id, limit=5)

    assert len(results) > 0
    top = results[0]
    assert "nginx" in top["content"].lower() or "负载均衡" in top["content"]
    assert top["metadata"] == {}
    assert top["distance"] < 0.5


# ── 4.2 PDF: page metadata → recall correct page ──


async def test_pdf_pipeline_with_page_metadata(db_session, real_embedder, test_project):
    """PDF upload should produce per-page chunks with page metadata."""
    pdf_bytes = create_test_pdf([
        "MySQL主从复制配置指南：配置master的binlog，设置server-id，创建复制用户。",
        "Redis哨兵模式部署：配置sentinel monitor，设置quorum，启动sentinel进程。",
        "Nginx反向代理配置：设置proxy_pass，配置upstream，添加健康检查。",
    ])

    service = DocumentService(session=db_session, embedder=real_embedder)
    doc = await service.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="ops-guide.pdf",
        file_bytes=pdf_bytes,
    )
    assert doc.doc_type == "pdf"
    assert doc.status == "ready"

    # Search for Redis content
    query_embedding = await real_embedder.embed_text("Redis哨兵模式部署")
    store = VectorStore(session=db_session)
    results = await store.search(query_embedding, test_project.id, limit=5)

    assert len(results) > 0
    # Find the result that contains Redis content
    redis_results = [r for r in results if "redis" in r["content"].lower() or "哨兵" in r["content"]]
    assert len(redis_results) > 0
    assert redis_results[0]["metadata"] == {"page": 2}


# ── 4.3 PPTX: slide metadata → recall correct slide ──


async def test_pptx_pipeline_with_slide_metadata(db_session, real_embedder, test_project):
    """PPTX upload should produce per-slide chunks with slide metadata."""
    pptx_bytes = create_test_pptx([
        "项目架构总览：前端React + 后端FastAPI + 数据库PostgreSQL",
        "Prometheus监控告警：配置alertmanager，设置告警规则，接入钉钉通知",
        "故障处理流程：发现 → 定位 → 修复 → 复盘",
    ])

    service = DocumentService(session=db_session, embedder=real_embedder)
    doc = await service.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="team-slides.pptx",
        file_bytes=pptx_bytes,
    )
    assert doc.doc_type == "pptx"

    # Search for Prometheus content
    query_embedding = await real_embedder.embed_text("Prometheus 监控告警配置")
    store = VectorStore(session=db_session)
    results = await store.search(query_embedding, test_project.id, limit=5)

    assert len(results) > 0
    prom_results = [r for r in results if "prometheus" in r["content"].lower() or "监控" in r["content"]]
    assert len(prom_results) > 0
    assert prom_results[0]["metadata"] == {"slide": 2}


# ── 4.4 Excel: sheet metadata → recall correct sheet ──


async def test_excel_pipeline_with_sheet_metadata(db_session, real_embedder, test_project):
    """Excel upload should produce per-sheet chunks with sheet metadata."""
    excel_bytes = create_test_excel({
        "服务端口": [
            ["服务名", "端口", "协议"],
            ["Nginx", "80", "HTTP"],
            ["MySQL", "3306", "TCP"],
            ["Redis", "6379", "TCP"],
        ],
        "告警规则": [
            ["指标", "阈值", "动作"],
            ["disk_usage", "90%", "发送钉钉告警"],
            ["cpu_usage", "95%", "自动扩容"],
        ],
    })

    service = DocumentService(session=db_session, embedder=real_embedder)
    doc = await service.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="infra-config.xlsx",
        file_bytes=excel_bytes,
    )
    assert doc.doc_type == "excel"

    # Search for MySQL port info
    query_embedding = await real_embedder.embed_text("MySQL 端口配置")
    store = VectorStore(session=db_session)
    results = await store.search(query_embedding, test_project.id, limit=5)

    assert len(results) > 0
    mysql_results = [r for r in results if "3306" in r["content"] or "MySQL" in r["content"]]
    assert len(mysql_results) > 0
    assert mysql_results[0]["metadata"] == {"sheet": "服务端口"}


# ── 4.5 Word: upload → store → search recall ──


async def test_word_pipeline(db_session, real_embedder, test_project):
    """Word (.docx) upload should produce chunks and be searchable."""
    docx_bytes = create_test_docx([
        "PostgreSQL 高可用方案",
        "使用 Patroni + etcd 实现自动故障切换，配置流复制和同步提交。",
        "监控指标包括：复制延迟、WAL 生成速率、连接数。",
    ])

    service = DocumentService(session=db_session, embedder=real_embedder)
    doc = await service.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="pg-ha.docx",
        file_bytes=docx_bytes,
    )
    assert doc.doc_type == "word"
    assert doc.status == "ready"

    # Search for Patroni content
    query_embedding = await real_embedder.embed_text("PostgreSQL Patroni 故障切换")
    store = VectorStore(session=db_session)
    results = await store.search(query_embedding, test_project.id, limit=5)

    assert len(results) > 0
    patroni_results = [
        r for r in results if "patroni" in r["content"].lower() or "故障切换" in r["content"]
    ]
    assert len(patroni_results) > 0
    # Word has no segment parser, metadata should be empty
    assert patroni_results[0]["metadata"] == {}


# ── 4.6 CSV: upload → store → search recall ──


async def test_csv_pipeline(db_session, real_embedder, test_project):
    """CSV upload should produce chunks and be searchable."""
    csv_bytes = create_test_csv(
        headers=["服务名", "端口", "状态", "负责人"],
        rows=[
            ["Nginx", "80", "running", "张三"],
            ["MySQL", "3306", "running", "李四"],
            ["Redis", "6379", "stopped", "王五"],
            ["Elasticsearch", "9200", "running", "赵六"],
        ],
    )

    service = DocumentService(session=db_session, embedder=real_embedder)
    doc = await service.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="services.csv",
        file_bytes=csv_bytes,
    )
    assert doc.doc_type == "csv"
    assert doc.status == "ready"

    # Search for Elasticsearch info
    query_embedding = await real_embedder.embed_text("Elasticsearch 端口和状态")
    store = VectorStore(session=db_session)
    results = await store.search(query_embedding, test_project.id, limit=5)

    assert len(results) > 0
    es_results = [r for r in results if "9200" in r["content"] or "Elasticsearch" in r["content"]]
    assert len(es_results) > 0
    # CSV has no segment parser, metadata should be empty
    assert es_results[0]["metadata"] == {}


# ── 4.7 Image: VL model describe → embed → recall ──


@pytest.mark.slow
async def test_image_pipeline_with_vl_model(
    db_session, real_embedder, real_image_describer, test_project
):
    """Image upload should call VL model, embed description, and be searchable."""
    image_bytes = create_test_image("Web Server → Database Architecture")

    service = DocumentService(
        session=db_session, embedder=real_embedder, image_describer=real_image_describer
    )
    doc = await service.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="architecture.png",
        file_bytes=image_bytes,
    )

    # VL output assertions
    assert doc.doc_type == "image"
    assert doc.status == "ready"
    assert len(doc.content) > 50  # VL model should produce a meaningful description

    # DB chunk assertions
    store = VectorStore(session=db_session)
    query_embedding = await real_embedder.embed_text("server architecture diagram")
    results = await store.search(query_embedding, test_project.id, limit=5)

    assert len(results) > 0
    image_results = [r for r in results if r["metadata"].get("source_type") == "image"]
    assert len(image_results) > 0

    # _format_source should include [图片]
    source_label = _format_source(image_results[0]["filename"], image_results[0]["metadata"])
    assert "[图片]" in source_label


# ── 4.6 Reranker ordering ──


async def test_reranker_orders_by_relevance(
    db_session, real_embedder, real_reranker, test_project
):
    """Reranker should put the most relevant document first."""
    service = DocumentService(session=db_session, embedder=real_embedder)

    docs = [
        ("k8s-scheduling.md", "Kubernetes 调度策略：Node Affinity、Taint/Toleration、Pod Priority。"),
        ("mysql-slow-query.md", "MySQL 慢查询优化：开启 slow_query_log，分析 explain 计划，添加索引。"),
        ("fastapi-intro.md", "FastAPI 入门教程：路由定义、请求参数验证、中间件配置。"),
    ]
    for filename, content in docs:
        await service.upload(
            project_id=test_project.id,
            filename=filename,
            content=content,
            doc_type="markdown",
        )

    # Vector search
    query = "MySQL 查询性能优化"
    query_embedding = await real_embedder.embed_text(query)
    store = VectorStore(session=db_session)
    candidates = await store.search(query_embedding, test_project.id, limit=20)

    assert len(candidates) >= 3

    # Rerank
    rerank_results = await real_reranker.rerank(
        query=query,
        documents=[c["content"] for c in candidates],
        top_n=3,
    )

    assert len(rerank_results) == 3

    # MySQL doc should rank first
    top_content = candidates[rerank_results[0].index]["content"]
    assert "mysql" in top_content.lower() or "慢查询" in top_content

    # Scores should be in descending order
    scores = [r.relevance_score for r in rerank_results]
    assert scores == sorted(scores, reverse=True)


# ── 4.7 search_knowledge_base() full flow ──


async def test_search_knowledge_base_full(db_session, real_embedder, test_project):
    """search_knowledge_base should return service_md + PDF chunks with source labels."""
    pdf_bytes = create_test_pdf([
        "MySQL主从复制原理：binlog同步，relay log回放，GTID模式。",
        "主从延迟排查：检查Seconds_Behind_Master，分析网络延迟，优化大事务。",
    ])

    service = DocumentService(session=db_session, embedder=real_embedder)
    await service.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="mysql-replication.pdf",
        file_bytes=pdf_bytes,
    )

    # Patch get_session_ctx to use our test session
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session_ctx():
        yield db_session

    with patch("src.tools.knowledge_tools.get_session_ctx", fake_session_ctx):
        result = await search_knowledge_base(
            query="MySQL主从复制延迟",
            project_id=str(test_project.id),
        )

    # Should contain service_md
    assert "服务架构" in result or "SERVICE.md" in result
    # Should contain PDF content
    assert "MySQL" in result or "mysql" in result.lower()
    # Should contain source labels with page numbers
    assert "页" in result
    # Should contain relevance score
    assert "相关度" in result


# ── 4.8 KB Sub-Agent with real search ──


async def test_kb_agent_with_real_search(db_session, real_embedder, test_project):
    """KB agent should call search tool (real DB) and produce a summary."""
    pdf_bytes = create_test_pdf([
        "MySQL主从复制配置：开启binlog，配置server-id，创建复制账号。",
        "主从延迟处理：并行复制、半同步复制、延迟监控告警。",
    ])

    service = DocumentService(session=db_session, embedder=real_embedder)
    await service.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="mysql-ha.pdf",
        file_bytes=pdf_bytes,
    )

    events = []

    async def capture_callback(event_type: str, data: dict):
        events.append({"event_type": event_type, "data": data})

    # FakeStreamingLLM: first call → invoke search tool, second call → summary
    class FakeStreamingLLM:
        def __init__(self, responses):
            self._responses = list(responses)
            self._call_index = 0

        def bind_tools(self, tools):
            return self

        async def astream(self, messages, **kwargs):
            if self._call_index >= len(self._responses):
                yield AIMessage(content="Done")
                return
            response = self._responses[self._call_index]
            self._call_index += 1
            yield response

    fake_responses = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "search_knowledge_base_tool",
                "args": {"query": "MySQL主从复制"},
                "id": "tc-int-1",
            }],
        ),
        AIMessage(content="根据知识库文档，MySQL主从复制需要配置binlog和server-id。"),
    ]

    fake_llm = FakeStreamingLLM(fake_responses)

    # Patch LLM but let search_knowledge_base hit real DB
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session_ctx():
        yield db_session

    with (
        patch("src.agent.sub_agents.kb_agent.ChatOpenAI", return_value=fake_llm),
        patch("src.tools.knowledge_tools.get_session_ctx", fake_session_ctx),
    ):
        from src.agent.sub_agents.kb_agent import run_kb_agent

        result = await run_kb_agent(
            title="MySQL主从同步延迟",
            description="从库 Seconds_Behind_Master 持续增长",
            project_id=str(test_project.id),
            event_callback=capture_callback,
        )

    # Agent produced a summary
    assert len(result) > 0
    assert "MySQL" in result or "mysql" in result.lower()

    # Events should include tool_call and tool_result
    event_types = [e["event_type"] for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types

    # tool_result should contain real content from DB
    tool_results = [e for e in events if e["event_type"] == "tool_result"]
    assert len(tool_results) > 0
    tool_output = tool_results[0]["data"]["output"]
    assert "MySQL" in tool_output or "binlog" in tool_output
    # Should have page source label
    assert "页" in tool_output


# ── 4.9 Mixed document types search ──


@pytest.mark.slow
async def test_mixed_document_types_search(
    db_session, real_embedder, real_image_describer, test_project
):
    """Search across markdown, PDF, and image documents."""
    service_text = DocumentService(session=db_session, embedder=real_embedder)
    service_img = DocumentService(
        session=db_session, embedder=real_embedder, image_describer=real_image_describer
    )

    # Upload markdown
    await service_text.upload(
        project_id=test_project.id,
        filename="nginx-config.md",
        content="Nginx 配置详解：worker_processes auto; events { worker_connections 1024; }",
        doc_type="markdown",
    )

    # Upload PDF
    pdf_bytes = create_test_pdf([
        "MySQL 备份策略：mysqldump 全量备份",
        "MySQL 增量备份：binlog 配合 mysqlbinlog 工具",
    ])
    await service_text.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="mysql-backup.pdf",
        file_bytes=pdf_bytes,
    )

    # Upload image
    image_bytes = create_test_image("System Architecture Diagram")
    await service_img.upload_file(
        project_id=test_project.id,
        project_slug=test_project.slug,
        filename="system-arch.png",
        file_bytes=image_bytes,
    )

    store = VectorStore(session=db_session)

    # Search for MySQL backup → PDF should rank high
    q1 = await real_embedder.embed_text("MySQL backup strategy")
    results1 = await store.search(q1, test_project.id, limit=10)
    assert len(results1) > 0
    # Find PDF results
    pdf_results = [r for r in results1 if "page" in r["metadata"]]
    assert len(pdf_results) > 0

    # Search for architecture diagram → image should appear
    q2 = await real_embedder.embed_text("architecture diagram")
    results2 = await store.search(q2, test_project.id, limit=10)
    assert len(results2) > 0
    image_results = [r for r in results2 if r["metadata"].get("source_type") == "image"]
    assert len(image_results) > 0
