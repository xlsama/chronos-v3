from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Server, ProjectDocument


def generate_service_map_template(
    project_name: str,
    servers: list[Server],
) -> str:
    lines = [f"# 服务架构 - {project_name}", ""]

    lines.append("## 服务器与服务")
    lines.append("")

    if servers:
        for s in servers:
            lines.append(f"### {s.name} ({s.username}@{s.host}:{s.port})")
            lines.append("")
            lines.append("> 请在下方列出此服务器上运行的服务")
            lines.append("")
            lines.append("- **服务名称**: (例如: MySQL, Redis, nginx)")
            lines.append("  - 端口:")
            lines.append("  - 说明:")
            lines.append("")
    else:
        lines.append("> 暂无关联服务器，请先添加服务器后再编辑此文档")
        lines.append("")

    lines.append("## 服务间关系")
    lines.append("")
    lines.append("> 请描述服务之间的调用/依赖关系")
    lines.append("> 例如: frontend -> backend API -> MySQL")
    lines.append("")

    lines.append("## 备注")
    lines.append("")
    lines.append("> 其他基础设施相关说明")
    lines.append("")

    return "\n".join(lines)


async def ensure_service_map(
    session: AsyncSession,
    project_id,
    project_name: str,
    servers: list[Server] | None = None,
) -> ProjectDocument | None:
    existing = (
        await session.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.doc_type == "service_map",
            )
        )
    ).scalar_one_or_none()

    if existing:
        return None

    if servers is None:
        servers = []

    content = generate_service_map_template(project_name, servers)
    doc = ProjectDocument(
        project_id=project_id,
        filename="SERVICE.md",
        content=content,
        doc_type="service_map",
        status="indexed",
    )
    session.add(doc)
    await session.flush()
    return doc
