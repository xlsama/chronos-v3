import uuid
from contextlib import asynccontextmanager

from sqlalchemy import select

from src.db.connection import get_session_factory
from src.db.models import Connection, Project, Service, ServiceConnectionBinding, ServiceDependency
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

        service_result = await session.execute(
            select(Service).where(Service.project_id == uuid.UUID(project_id)).order_by(Service.name)
        )
        dependency_result = await session.execute(
            select(ServiceDependency).where(ServiceDependency.project_id == uuid.UUID(project_id))
        )
        connection_result = await session.execute(
            select(Connection).where(Connection.project_id == uuid.UUID(project_id)).order_by(Connection.name)
        )
        binding_result = await session.execute(
            select(ServiceConnectionBinding).where(ServiceConnectionBinding.project_id == uuid.UUID(project_id))
        )

        services = list(service_result.scalars().all())
        dependencies = list(dependency_result.scalars().all())
        connections = list(connection_result.scalars().all())
        bindings = list(binding_result.scalars().all())

        if services:
            service_lines = []
            for service in services:
                service_lines.append(f"### {service.name} ({service.service_type}, id: {service.id})")
                if service.description:
                    service_lines.append(f"- 描述: {service.description}")
                if service.business_context:
                    service_lines.append(f"- 业务上下文: {service.business_context}")
                if service.keywords:
                    service_lines.append(f"- 关键词: {', '.join(service.keywords)}")
                service_lines.append(f"- 状态: {service.status}")
            sections.append("## 服务拓扑\n\n" + "\n".join(service_lines))

        if dependencies:
            service_name_map = {str(service.id): service.name for service in services}
            dependency_lines = []
            for dependency in dependencies:
                dependency_lines.append(
                    f"- {service_name_map.get(str(dependency.from_service_id), str(dependency.from_service_id))} "
                    f"--[{dependency.dependency_type}]--> "
                    f"{service_name_map.get(str(dependency.to_service_id), str(dependency.to_service_id))}"
                )
            sections.append("## 服务依赖\n\n" + "\n".join(dependency_lines))

        if connections:
            connection_lines = []
            for conn in connections:
                connection_lines.append(f"### {conn.name} ({conn.type}, id: {conn.id})")
                if conn.description:
                    connection_lines.append(f"- 描述: {conn.description}")
                connection_lines.append(f"- 状态: {conn.status}")
                if conn.host:
                    connection_lines.append(f"- 入口: {conn.username}@{conn.host}:{conn.port}")
                if conn.capabilities:
                    connection_lines.append(f"- 能力: {', '.join(conn.capabilities)}")
            sections.append("## 执行入口\n\n" + "\n".join(connection_lines))

        if bindings:
            service_name_map = {str(service.id): service.name for service in services}
            connection_name_map = {str(conn.id): conn.name for conn in connections}
            binding_lines = []
            for binding in bindings:
                binding_lines.append(
                    f"- {service_name_map.get(str(binding.service_id), str(binding.service_id))} -> "
                    f"{connection_name_map.get(str(binding.connection_id), str(binding.connection_id))} "
                    f"({binding.usage_type}, priority={binding.priority})"
                )
            sections.append("## 服务与执行入口绑定\n\n" + "\n".join(binding_lines))

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
