import uuid
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.connection import get_session_factory
from src.db.models import Infrastructure, Project
from src.db.vector_store import VectorStore
from src.lib.embedder import Embedder


@asynccontextmanager
async def get_session_ctx():
    factory = get_session_factory()
    async with factory() as session:
        yield session


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

        # Query infrastructure + services for structured data
        infra_result = await session.execute(
            select(Infrastructure)
            .options(selectinload(Infrastructure.services))
            .where(Infrastructure.project_id == uuid.UUID(project_id))
        )
        infras = infra_result.scalars().all()

        if infras:
            infra_lines = []
            for infra in infras:
                infra_lines.append(
                    f"### {infra.name} (type: {infra.type}, id: {infra.id})"
                )
                infra_lines.append(f"- 状态: {infra.status}")
                if infra.host:
                    infra_lines.append(f"- 主机: {infra.host}:{infra.port}")
                if infra.services:
                    infra_lines.append("- 服务列表:")
                    for svc in infra.services:
                        svc_info = f"  - **{svc.name}** (type: {svc.service_type}, status: {svc.status})"
                        if svc.port:
                            svc_info += f", port: {svc.port}"
                        if svc.namespace:
                            svc_info += f", namespace: {svc.namespace}"
                        infra_lines.append(svc_info)
                else:
                    infra_lines.append("- 服务列表: (暂无)")
            sections.append(
                "## 关联基础设施与服务\n\n" + "\n".join(infra_lines)
            )

        # Vector search for relevant document chunks
        embedder = Embedder()
        query_embedding = await embedder.embed_text(query)

        store = VectorStore(session=session)
        results = await store.search(query_embedding, uuid.UUID(project_id), limit=5)

        if results:
            chunks_text = "\n\n".join(
                f"**[{r['filename']}]** (相关度: {1 - r['distance']:.2f})\n{r['content']}"
                for r in results
            )
            sections.append(f"## 相关文档片段\n\n{chunks_text}")

        if not sections:
            return "没有找到与查询相关的知识库内容。"

        return "\n\n---\n\n".join(sections)
