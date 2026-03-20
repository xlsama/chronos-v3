import time
import uuid
from contextlib import asynccontextmanager

import orjson
from sqlalchemy import select

from src.db.connection import get_session_factory
from src.db.models import Project, ProjectDocument
from src.db.vector_store import VectorStore
from src.lib.embedder import Embedder
from src.lib.logger import logger
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
    """List all projects as JSON with descriptions and AGENTS.md preview for matching."""
    async with get_session_ctx() as session:
        result = await session.execute(
            select(Project).order_by(Project.created_at.desc())
        )
        projects = list(result.scalars().all())
        logger.info(f"[knowledge] list_projects_for_matching: {len(projects)} projects")
        if not projects:
            return "[]"

        items = []
        for project in projects:
            agents_result = await session.execute(
                select(ProjectDocument).where(
                    ProjectDocument.project_id == project.id,
                    ProjectDocument.doc_type == "agents_config",
                ).limit(1)
            )
            agents_doc = agents_result.scalar_one_or_none()
            has_agents_md = bool(agents_doc and agents_doc.content.strip())

            items.append({
                "project_id": str(project.id),
                "project_name": project.name,
                "description": project.description or "",
                "has_agents_md": has_agents_md,
                "agents_md_preview": (agents_doc.content[:300] + "...") if has_agents_md else "",
            })
        return orjson.dumps(items).decode()


async def search_knowledge_base(query: str, project_id: str) -> tuple[str, list[dict]]:
    """Search the project knowledge base for relevant context.

    Args:
        query: The search query describing what information you need.
        project_id: The project ID to search within.

    Returns:
        Tuple of (formatted text, sources list).
    """
    t_total = time.monotonic()
    logger.info(f"[knowledge] search_knowledge_base: query={query[:100]}, project_id={project_id}")
    async with get_session_ctx() as session:
        project = await session.get(Project, uuid.UUID(project_id))
        if not project:
            return (f"未找到项目 (ID: {project_id})", [])

        sections = []
        sources: list[dict] = []
        seen_doc_ids: set[str] = set()

        # Read AGENTS.md (raw content, not vector search)
        agents_result = await session.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == uuid.UUID(project_id),
                ProjectDocument.doc_type == "agents_config",
            ).limit(1)
        )
        agents_doc = agents_result.scalar_one_or_none()

        sections.append(f"## 项目: {project.name} (ID: {project.id})")

        if agents_doc and agents_doc.content.strip():
            sections.append(f"### AGENTS.md\n{agents_doc.content}")
            sources.append({"type": "document", "id": str(agents_doc.id), "filename": agents_doc.filename})
            seen_doc_ids.add(str(agents_doc.id))
        else:
            sections.append("### AGENTS.md\n[空 - 未配置服务信息]")

        # Vector search for relevant document chunks
        embedder = _get_embedder()
        reranker = _get_reranker()

        t_embed = time.monotonic()
        query_embedding = await embedder.embed_text(query)
        embed_elapsed = time.monotonic() - t_embed
        logger.info(f"[knowledge] Embedding computed in {embed_elapsed:.2f}s")

        store = VectorStore(session=session)
        candidates = await store.search(query_embedding, uuid.UUID(project_id), limit=20)
        logger.info(f"[knowledge] Vector search returned {len(candidates)} candidates")

        if candidates:
            t_rerank = time.monotonic()
            rerank_results = await reranker.rerank(
                query=query,
                documents=[c["content"] for c in candidates],
                top_n=3,
            )
            rerank_elapsed = time.monotonic() - t_rerank
            results = []
            for rr in rerank_results:
                item = candidates[rr.index].copy()
                item["relevance_score"] = rr.relevance_score
                results.append(item)
            top_scores = [f"{r['relevance_score']:.2f}" for r in results]
            logger.info(f"[knowledge] Rerank completed in {rerank_elapsed:.2f}s: {len(results)} results, scores={top_scores}")
        else:
            results = []

        if results:
            chunks_text = "\n\n".join(
                f"**[{_format_source(r['filename'], r.get('metadata', {}))}]** (相关度: {r['relevance_score']:.2f})\n{r['content']}"
                for r in results
            )
            sections.append(f"### 相关文档\n\n{chunks_text}")

            # Collect unique document sources
            for r in results:
                doc_id = r["document_id"]
                if doc_id not in seen_doc_ids:
                    seen_doc_ids.add(doc_id)
                    source: dict = {"type": "document", "id": doc_id, "filename": r["filename"]}
                    if "page" in r.get("metadata", {}):
                        source["page"] = r["metadata"]["page"]
                    sources.append(source)

        if len(sections) <= 1:
            total_elapsed = time.monotonic() - t_total
            logger.info(f"[knowledge] search_knowledge_base completed in {total_elapsed:.2f}s: no results")
            return ("没有找到与查询相关的知识库内容。", [])

        total_elapsed = time.monotonic() - t_total
        logger.info(f"[knowledge] search_knowledge_base completed in {total_elapsed:.2f}s")
        return ("\n\n---\n\n".join(sections), sources)
