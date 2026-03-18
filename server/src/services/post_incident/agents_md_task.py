import uuid
from collections import defaultdict

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_session_factory
from src.db.models import DocumentChunk, ProjectDocument
from src.lib.embedder import Embedder
from src.lib.logger import logger
from src.services.post_incident.base import format_messages_for_extraction, get_mini_llm

EXTRACT_KNOWLEDGE_PROMPT = """\
你是一个运维知识提取器。从以下事件排查过程中提取可复用的运维知识。

提取内容:
- 服务配置（端口、路径、配置文件位置等）
- 排查方法论（如何定位此类问题）
- 服务间依赖关系
- 关键发现/陷阱（容易踩坑的地方）
- 修复方案

只提取事实性的、可复用的知识，不要一次性信息（如具体的时间戳、临时文件名等）。
无可提取知识则只输出 "NO_KNOWLEDGE"。"""

SHOULD_UPDATE_PROMPT = """\
你是 AGENTS.md 文档维护助手。判断是否需要将新知识更新到 AGENTS.md。

规则:
1. 完全重复的内容 → 只输出 "NO_UPDATE"
2. 有价值的补充 → 输出更新后的完整 AGENTS.md 内容
3. 保持现有结构，增量补充新知识
4. 不要删除现有内容
5. 若当前 AGENTS.md 为空，创建合理的初始结构

当前 AGENTS.md 内容:
```
{current_content}
```

新提取的运维知识:
```
{knowledge_text}
```

如果无需更新只输出 "NO_UPDATE"，否则输出更新后的完整 AGENTS.md 内容（纯 Markdown，不要用代码块包裹）。"""


async def auto_update_agents_md(
    incident_id: str,
    summary_md: str,
    messages: list,
    description: str,
) -> dict:
    """主入口。纯向量搜索匹配项目，不依赖 incident 的 project_id。"""
    sid = incident_id[:8]
    logger.info(f"[{sid}] [agents_md] Starting AGENTS.md auto-update")

    # Step 1: Extract operational knowledge
    knowledge_text = await _extract_knowledge(messages, summary_md, description)
    if not knowledge_text:
        logger.info(f"[{sid}] [agents_md] No knowledge extracted, skipping")
        return {"action": "no_knowledge"}

    logger.info(f"[{sid}] [agents_md] Knowledge extracted ({len(knowledge_text)} chars)")

    # Step 2: Find candidate projects via vector search
    candidates = await _find_candidate_projects(knowledge_text)
    if not candidates:
        logger.info(f"[{sid}] [agents_md] No candidate projects found")
        return {"action": "no_candidates"}

    logger.info(f"[{sid}] [agents_md] Found {len(candidates)} candidate project(s)")

    # Step 3: Update each candidate project's AGENTS.md
    results = {}
    for project_id, distance in candidates:
        async with get_session_factory()() as session:
            result = await _update_project_agents_md(session, project_id, knowledge_text)
            results[str(project_id)] = result
            logger.info(f"[{sid}] [agents_md] Project {str(project_id)[:8]}: {result} (distance={distance:.4f})")

    return {"action": "completed", "results": results}


async def _extract_knowledge(messages: list, summary_md: str, description: str) -> str | None:
    """LLM 提取运维知识。返回 None 表示无可提取知识。"""
    conversation_text = format_messages_for_extraction(messages, description)
    # Truncate to avoid token limits
    input_text = f"## 排查过程\n{conversation_text[:6000]}\n\n## 排查结论\n{summary_md[:3000]}"

    llm = get_mini_llm()
    resp = await llm.ainvoke([
        SystemMessage(content=EXTRACT_KNOWLEDGE_PROMPT),
        HumanMessage(content=input_text),
    ])
    result = resp.content.strip()
    if result == "NO_KNOWLEDGE" or len(result) < 20:
        return None
    return result


async def _find_candidate_projects(knowledge_text: str) -> list[tuple[uuid.UUID, float]]:
    """向量搜索 DocumentChunk，按 project_id 分组取 top 项目。"""
    embedder = Embedder()
    embedding = await embedder.embed_text(knowledge_text)

    async with get_session_factory()() as session:
        # Search across all projects (no project_id filter)
        stmt = (
            select(
                DocumentChunk.project_id,
                DocumentChunk.embedding.cosine_distance(embedding).label("distance"),
            )
            .where(DocumentChunk.embedding.isnot(None))
            .order_by("distance")
            .limit(30)
        )
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        return []

    # Group by project_id, keep best (lowest) distance per project
    best_by_project: dict[uuid.UUID, float] = {}
    for row in rows:
        pid = row.project_id
        dist = row.distance
        if pid not in best_by_project or dist < best_by_project[pid]:
            best_by_project[pid] = dist

    # Filter: only keep projects with distance < 0.3
    candidates = [
        (pid, dist) for pid, dist in best_by_project.items() if dist < 0.3
    ]
    # Sort by distance ascending
    candidates.sort(key=lambda x: x[1])
    return candidates


async def _update_project_agents_md(
    session: AsyncSession,
    project_id: uuid.UUID,
    knowledge_text: str,
) -> str:
    """读取项目 AGENTS.md，LLM 判断并执行更新。
    返回 "updated" | "skipped" | "no_doc"
    """
    # Find the AGENTS.md document
    result = await session.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.doc_type == "agents_config",
        ).limit(1)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return "no_doc"

    current_content = doc.content or ""

    # Ask LLM whether to update
    llm = get_mini_llm()
    prompt = SHOULD_UPDATE_PROMPT.format(
        current_content=current_content if current_content.strip() else "(空)",
        knowledge_text=knowledge_text,
    )
    resp = await llm.ainvoke([
        HumanMessage(content=prompt),
    ])
    result_text = resp.content.strip()

    if result_text == "NO_UPDATE":
        return "skipped"

    # Remove markdown code block wrapper if present
    if result_text.startswith("```"):
        lines = result_text.split("\n")
        # Remove first and last lines (```markdown and ```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        result_text = "\n".join(lines)

    # Update the document content
    doc.content = result_text
    doc.status = "indexed"
    await session.commit()
    return "updated"
