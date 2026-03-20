import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

import orjson
from sqlalchemy import select

from src.db.connection import get_session_factory
from src.db.models import Project, ProjectDocument
from src.db.vector_store import VectorStore
from src.lib.embedder import Embedder
from src.lib.logger import get_logger
from src.lib.reranker import Reranker

log = get_logger(component="knowledge")

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
        log.info("list_projects_for_matching", project_count=len(projects))
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
        result_json = orjson.dumps(items).decode()
        log.debug("list_projects_for_matching result", result=result_json)
        return result_json


async def search_knowledge_base(query: str) -> tuple[str, list[dict]]:
    """Search across all projects' knowledge base for relevant context.

    Args:
        query: The search query describing what information you need.

    Returns:
        Tuple of (formatted text grouped by project, sources list).
    """
    t_total = time.monotonic()
    log.info("search_knowledge_base", query_len=len(query))
    log.debug("search_knowledge_base", query=query)
    async with get_session_ctx() as session:
        embedder = _get_embedder()
        reranker = _get_reranker()

        t_embed = time.monotonic()
        query_embedding = await embedder.embed_text(query)
        embed_elapsed = time.monotonic() - t_embed
        log.info("Embedding computed", elapsed=f"{embed_elapsed:.2f}s")

        store = VectorStore(session=session)
        candidates = await store.search_all(query_embedding, limit=20)
        log.info("Vector search returned", candidate_count=len(candidates))
        for idx, c in enumerate(candidates):
            log.debug(
                "Vector candidate",
                index=idx,
                project_name=c.get("project_name"),
                filename=c.get("filename"),
                distance=c.get("distance"),
                content_preview=c.get("content", "")[:200],
            )

        if candidates:
            t_rerank = time.monotonic()
            rerank_results = await reranker.rerank(
                query=query,
                documents=[c["content"] for c in candidates],
                top_n=5,
            )
            rerank_elapsed = time.monotonic() - t_rerank
            results = []
            for rr in rerank_results:
                item = candidates[rr.index].copy()
                item["relevance_score"] = rr.relevance_score
                results.append(item)
            top_scores = [f"{r['relevance_score']:.2f}" for r in results]
            log.info("Rerank completed", elapsed=f"{rerank_elapsed:.2f}s", result_count=len(results), scores=top_scores)
            for idx, r in enumerate(results):
                log.debug(
                    "Rerank result",
                    index=idx,
                    project_name=r.get("project_name"),
                    filename=r.get("filename"),
                    relevance_score=r.get("relevance_score"),
                    content_preview=r.get("content", "")[:200],
                )
        else:
            results = []

        if not results:
            total_elapsed = time.monotonic() - t_total
            log.info("search_knowledge_base completed", elapsed=f"{total_elapsed:.2f}s", result_count=0)
            return ("没有找到与查询相关的知识库内容。", [])

        # Group results by project
        by_project: dict[str, list[dict]] = defaultdict(list)
        project_meta: dict[str, dict] = {}
        for r in results:
            pid = r["project_id"]
            by_project[pid].append(r)
            if pid not in project_meta:
                project_meta[pid] = {
                    "project_name": r["project_name"],
                    "project_description": r["project_description"],
                }

        sections = []
        sources: list[dict] = []
        seen_doc_ids: set[str] = set()

        for pid, chunks in by_project.items():
            meta = project_meta[pid]
            section_parts = [f"## 项目: {meta['project_name']} (ID: {pid})"]
            if meta["project_description"]:
                section_parts.append(f"描述: {meta['project_description']}")

            chunks_text = "\n\n".join(
                f"**[{_format_source(r['filename'], r.get('metadata', {}))}]** (相关度: {r['relevance_score']:.2f})\n{r['content']}"
                for r in chunks
            )
            section_parts.append(f"\n{chunks_text}")
            sections.append("\n".join(section_parts))

            for r in chunks:
                doc_id = r["document_id"]
                if doc_id not in seen_doc_ids:
                    seen_doc_ids.add(doc_id)
                    source: dict = {"type": "document", "id": doc_id, "filename": r["filename"]}
                    if "page" in r.get("metadata", {}):
                        source["page"] = r["metadata"]["page"]
                    sources.append(source)

        for pid, chunks in by_project.items():
            log.info(
                "Project group",
                project_id=pid,
                project_name=project_meta[pid]["project_name"],
                chunk_count=len(chunks),
            )

        formatted_text = "\n\n---\n\n".join(sections)
        total_elapsed = time.monotonic() - t_total
        log.info("search_knowledge_base completed", elapsed=f"{total_elapsed:.2f}s", project_count=len(by_project))
        log.debug("search_knowledge_base formatted_text", formatted_text=formatted_text)
        return (formatted_text, sources)


async def get_agents_md(project_ids: list[str]) -> str:
    """Batch read AGENTS.md for multiple projects.

    Args:
        project_ids: List of project UUIDs to read AGENTS.md from.

    Returns:
        Formatted text with AGENTS.md content per project.
    """
    log.info("get_agents_md", project_ids=project_ids)
    if not project_ids:
        return "未提供项目 ID。"

    async with get_session_ctx() as session:
        uuids = [uuid.UUID(pid) for pid in project_ids]
        # Fetch projects
        project_result = await session.execute(
            select(Project).where(Project.id.in_(uuids))
        )
        projects = {p.id: p for p in project_result.scalars().all()}

        # Fetch AGENTS.md documents
        agents_result = await session.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id.in_(uuids),
                ProjectDocument.doc_type == "agents_config",
            )
        )
        agents_docs = {doc.project_id: doc for doc in agents_result.scalars().all()}

        sections = []
        for pid_uuid in uuids:
            project = projects.get(pid_uuid)
            if not project:
                sections.append(f"## 项目: 未找到 (ID: {pid_uuid})\n[项目不存在]")
                log.info("get_agents_md project", project_id=str(pid_uuid), project_name="NOT_FOUND", content_len=0, is_empty=True)
                continue

            doc = agents_docs.get(pid_uuid)
            content = doc.content.strip() if doc and doc.content else ""
            is_empty = not content
            header = f"## 项目: {project.name} (ID: {pid_uuid})"
            if not is_empty:
                sections.append(f"{header}\n\n### AGENTS.md\n{doc.content}")
            else:
                sections.append(f"{header}\n\n### AGENTS.md\n[空 - 未配置服务信息]")
            log.info(
                "get_agents_md project",
                project_id=str(pid_uuid),
                project_name=project.name,
                content_len=len(content),
                is_empty=is_empty,
            )

        formatted_text = "\n\n---\n\n".join(sections)
        log.info("get_agents_md completed", project_count=len(sections))
        log.debug("get_agents_md formatted_text", formatted_text=formatted_text)
        return formatted_text
