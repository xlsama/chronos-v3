import uuid
from contextlib import asynccontextmanager

from sqlalchemy import select

from src.db.connection import get_session_factory
from src.db.models import Server, Project, ProjectDocument
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


async def list_projects_for_matching() -> str:
    """List all projects with their descriptions and linked servers for matching.

    Returns:
        Formatted string with all project information.
    """
    async with get_session_ctx() as session:
        result = await session.execute(
            select(Project).order_by(Project.created_at.desc())
        )
        projects = list(result.scalars().all())

        if not projects:
            return "当前没有任何项目。"

        sections = []
        for project in projects:
            lines = [f"## 项目: {project.name} (ID: {project.id})"]
            if project.description:
                lines.append(f"描述: {project.description}")

            # Get linked servers
            server_ids = [uuid.UUID(sid) for sid in (project.linked_server_ids or [])]
            if server_ids:
                server_result = await session.execute(
                    select(Server).where(Server.id.in_(server_ids))
                )
                servers = list(server_result.scalars().all())
                if servers:
                    lines.append("关联服务器:")
                    for s in servers:
                        host_info = f", host: {s.host}" if s.host else ""
                        lines.append(f"  - {s.name} (ID: {s.id}{host_info})")

            sections.append("\n".join(lines))

        return "\n---\n".join(sections)


async def search_knowledge_base(query: str, project_id: str) -> tuple[str, list[dict]]:
    """Search the project knowledge base for relevant context.

    Args:
        query: The search query describing what information you need.
        project_id: The project ID to search within.

    Returns:
        Tuple of (formatted text, sources list).
    """
    async with get_session_ctx() as session:
        project = await session.get(Project, uuid.UUID(project_id))
        if not project:
            return (f"未找到项目 (ID: {project_id})", [])

        sections = []
        sources: list[dict] = []
        seen_doc_ids: set[str] = set()

        # Get SERVICE.md
        service_map_result = await session.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == uuid.UUID(project_id),
                ProjectDocument.doc_type == "service_map",
            ).limit(1)
        )
        service_map = service_map_result.scalar_one_or_none()
        if service_map:
            sections.append(f"## 服务架构\n\n{service_map.content}")
            sources.append({"type": "document", "id": str(service_map.id), "filename": service_map.filename})
            seen_doc_ids.add(str(service_map.id))

        # Get servers via project.linked_server_ids
        server_ids = [uuid.UUID(sid) for sid in (project.linked_server_ids or [])]
        if server_ids:
            server_result = await session.execute(
                select(Server).where(
                    Server.id.in_(server_ids),
                    Server.status != "offline",
                ).order_by(Server.name)
            )
            servers = list(server_result.scalars().all())
        else:
            servers = []

        if servers:
            server_lines = []
            for s in servers:
                server_lines.append(f"### {s.name} (SSH, id: {s.id})")
                if s.description:
                    server_lines.append(f"- 描述: {s.description}")
                server_lines.append(f"- 状态: {s.status}")
                if s.host:
                    server_lines.append(f"- 入口: {s.username}@{s.host}:{s.port}")
            sections.append("## 执行入口\n\n" + "\n".join(server_lines))

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

            # Collect unique document sources
            for r in results:
                doc_id = r["document_id"]
                if doc_id not in seen_doc_ids:
                    seen_doc_ids.add(doc_id)
                    source: dict = {"type": "document", "id": doc_id, "filename": r["filename"]}
                    if "page" in r.get("metadata", {}):
                        source["page"] = r["metadata"]["page"]
                    sources.append(source)

        if not sections:
            return ("没有找到与查询相关的知识库内容。", [])

        return ("\n\n---\n\n".join(sections), sources)
