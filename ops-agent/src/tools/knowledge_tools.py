import uuid
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.connection import get_session_factory
from src.db.models import Connection, Project
from src.db.vector_store import VectorStore
from src.lib.embedder import Embedder
from src.lib.reranker import Reranker


_embedder_instance: Embedder | None = None
_reranker_instance: Reranker | None = None


def _get_embedder() -> Embedder:
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = Embedder()
    return _embedder_instance


def _get_reranker() -> Reranker:
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = Reranker()
    return _reranker_instance


@asynccontextmanager
async def get_session_ctx():
    factory = get_session_factory()
    async with factory() as session:
        yield session


def _format_source(filename: str, metadata: dict) -> str:
    """Format a source label from filename and chunk metadata."""
    label = filename
    if "page" in metadata:
        label += f", 第{metadata['page']}页"
    elif "slide" in metadata:
        label += f", 第{metadata['slide']}张幻灯片"
    elif "sheet" in metadata:
        label += f", 工作表: {metadata['sheet']}"
    if metadata.get("source_type") == "image":
        label += " [图片]"
    return label


async def search_knowledge_base(query: str, project_id: str) -> str:
    """Search the project knowledge base for relevant context.

    Args:
        query: The search query describing what information you need.
        project_id: The project ID to search within.

    Returns:
        Formatted string with relevant knowledge base context.
    """
    async with get_session_ctx() as session:
        project = await session.get(Project, uuid.UUID(project_id))
        if not project:
            return f"未找到项目 (ID: {project_id})"

        sections = []

        # Include SERVICE.md if present
        if project.service_md:
            sections.append(f"## 项目架构文档 (SERVICE.md)\n\n{project.service_md}")

        # Query connections + services for structured data
        conn_result = await session.execute(
            select(Connection)
            .options(selectinload(Connection.services))
            .where(Connection.project_id == uuid.UUID(project_id))
        )
        conns = conn_result.scalars().all()

        if conns:
            conn_lines = []
            for conn in conns:
                conn_lines.append(
                    f"### {conn.name} (type: {conn.type}, id: {conn.id})"
                )
                conn_lines.append(f"- 状态: {conn.status}")
                if conn.host:
                    conn_lines.append(f"- 主机: {conn.host}:{conn.port}")
                if conn.services:
                    conn_lines.append("- 服务列表:")
                    for svc in conn.services:
                        svc_info = f"  - **{svc.name}** (port: {svc.port}, status: {svc.status})"
                        if svc.namespace:
                            svc_info += f", namespace: {svc.namespace}"
                        conn_lines.append(svc_info)
                else:
                    conn_lines.append("- 服务列表: (暂无)")
            sections.append(
                "## 关联连接与服务\n\n" + "\n".join(conn_lines)
            )

        # Vector search for relevant document chunks
        embedder = _get_embedder()
        reranker = _get_reranker()
        query_embedding = await embedder.embed_text(query)

        store = VectorStore(session=session)
        candidates = await store.search(query_embedding, uuid.UUID(project_id), limit=20)

        if candidates:
            rerank_results = await reranker.rerank(
                query=query,
                documents=[c["content"] for c in candidates],
                top_n=5,
            )
            results = []
            for rr in rerank_results:
                item = candidates[rr.index].copy()
                item["relevance_score"] = rr.relevance_score
                results.append(item)
        else:
            results = []

        if results:
            chunks_text = "\n\n".join(
                f"**[{_format_source(r['filename'], r.get('metadata', {}))}]** (相关度: {r['relevance_score']:.2f})\n{r['content']}"
                for r in results
            )
            sections.append(f"## 相关文档片段\n\n{chunks_text}")

        if not sections:
            return "没有找到与查询相关的知识库内容。"

        return "\n\n---\n\n".join(sections)
