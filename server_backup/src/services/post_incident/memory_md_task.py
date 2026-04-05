import re
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_session_factory
from src.db.models import DocumentChunk, Project, ProjectDocument, Server, Service
from src.lib.embedder import Embedder
from src.lib.logger import get_logger
from src.services.post_incident.base import get_mini_llm

# ---------------------------------------------------------------------------
# MEMORY.md 标准模板（extract 和 update 共享）
# ---------------------------------------------------------------------------

_MEMORY_MD_TEMPLATE = """\
# 项目运维手册

## 架构拓扑

### Servers
| Server 名称 | Host/IP | 用途 |
|---|---|---|
| prod-web-01 | 10.0.1.10 | Web 应用服务器 |

### Services
| Service 名称 | 类型 | 所在 Server | 端口 | 说明 |
|---|---|---|---|---|
| nginx | Nginx | prod-web-01 | 80/443 | 反向代理 |

### 架构图
[Mermaid flowchart TD，节点 ID 与 Services 表一致]

## 服务配置
[固定配置: 配置文件路径、端口、API 端点。不含故障推断值]

## 运维信息

### 部署方式
[Docker Compose / K8s / 直接部署]

### 日志路径
| 服务 | 日志位置 | 说明 |

### 健康检查
| 服务 | 端点 | 预期响应 |"""


EXTRACT_KNOWLEDGE_PROMPT = """\
你是运维知识提取器。从事件排查过程中提取可复用的运维知识。

重点提取:
1. **Server 与 Service 拓扑**: 名称、IP/Host、类型、端口、归属关系、依赖关系
2. **服务配置**: 端口、路径、配置文件位置（仅固定值，不含故障推断值）
3. **运维信息**: 部署方式、日志路径、健康检查端点

规则:
- 只提取基础设施层面的静态知识（即使没有事件也成立的信息）
- 不要一次性信息（时间戳、临时文件名）
- **严禁提取事件特定信息**: 错误信息、异常日志特征、排查关键词、根因分析、故障恢复步骤、故障推断的配置值
- Server/Service 名称与系统中已配置的保持一致
{entity_anchors}
- 无可提取知识则只输出 "NO_KNOWLEDGE"
"""

SHOULD_UPDATE_PROMPT = (
    """\
你是 MEMORY.md 文档维护助手。判断是否需要将新知识更新到 MEMORY.md。

## MEMORY.md 标准结构

````markdown
"""
    + _MEMORY_MD_TEMPLATE
    + """
````

## 架构图规范
- `flowchart TD`，不用 subgraph
- 节点 ID 用短横线（如 `app-backend`），与 Services 表一致
- 节点标签含：服务名、端口、所在 Server
- 依赖关系: `A -->|描述| B`
- 优先保证语法正确性

## 更新规则
1. 完全重复 → 只输出 "NO_UPDATE"
2. 有价值补充 → 输出更新后的完整 MEMORY.md
3. 保持现有内容不变，只增量补充
4. 新 Server/Service → 加表格行 + 架构图节点
5. MEMORY.md 为空时按标准结构创建
6. 不编造信息
7. 只允许标准章节，禁止新增事件衍生章节
8. 禁止写入事件特定内容（错误信息、根因、修复步骤）。现有内容中有此类信息应移除

## 当前 MEMORY.md 内容
```
{current_content}
```

## 新提取的运维知识
```
{knowledge_text}
```

如果无需更新只输出 "NO_UPDATE"，否则输出更新后的完整 MEMORY.md 内容（纯 Markdown，不要用代码块包裹）。"""
)


async def _fetch_entity_anchors(session: AsyncSession) -> str:
    """查询所有已配置的 Server 和 Service，格式化为实体参照表。"""
    log = get_logger(component="post_incident")
    servers = (await session.execute(select(Server.name, Server.host).order_by(Server.name))).all()
    services = (
        await session.execute(
            select(Service.name, Service.service_type, Service.host, Service.port).order_by(
                Service.name
            )
        )
    ).all()

    log.info("Fetched entity anchors", servers=len(servers), services=len(services))

    if not servers and not services:
        log.info("No entity anchors found, will use empty anchors")
        return ""

    lines = ["\n## 系统已配置的实体（提取时优先匹配这些名称，通过 IP/Host 关联）"]
    if servers:
        lines.append("\n### Servers")
        for s in servers:
            lines.append(f"- {s.name} ({s.host})")
    if services:
        lines.append("\n### Services")
        for s in services:
            lines.append(f"- {s.name} [{s.service_type}] @ {s.host}:{s.port}")

    result = "\n".join(lines)
    log.debug("Entity anchors content", content=result)
    return result


async def auto_update_memory_md(
    incident_id: str,
    summary_md: str,
    conversation_text: str,
    kb_project_ids: list[str] | None = None,
) -> dict:
    """主入口。向量搜索匹配项目，KB Agent 已匹配的项目作为必选候选。"""
    sid = incident_id[:8]
    log = get_logger(component="post_incident", sid=sid)
    log.info("Starting MEMORY.md auto-update")

    # Step 0: Fetch entity anchors for knowledge extraction
    log.info("Fetching entity anchors from DB")
    async with get_session_factory()() as session:
        entity_anchors = await _fetch_entity_anchors(session)
    log.info("Entity anchors ready", length=len(entity_anchors))

    # Step 1: Extract operational knowledge
    log.info(
        "Extracting knowledge from conversation",
        conv_len=len(conversation_text),
        summary_len=len(summary_md),
    )
    t_step = time.monotonic()
    knowledge_text = await _extract_knowledge(conversation_text, summary_md, entity_anchors)
    extract_elapsed = time.monotonic() - t_step
    log.info("Knowledge extraction completed", elapsed=f"{extract_elapsed:.2f}s")
    if not knowledge_text:
        log.info("No knowledge extracted, skipping")
        return {"action": "no_knowledge"}

    log.info("Knowledge extracted", chars=len(knowledge_text))

    # Step 2: Find candidate projects via vector search
    t_step = time.monotonic()
    candidates = await _find_candidate_projects(knowledge_text)
    find_elapsed = time.monotonic() - t_step
    log.info("Candidate project search completed", elapsed=f"{find_elapsed:.2f}s")

    # 确保 KB Agent 匹配的项目在候选列表中
    if kb_project_ids:
        existing_pids = {c[0] for c in candidates}
        for kb_pid_str in kb_project_ids:
            pid = uuid.UUID(kb_pid_str)
            if pid not in existing_pids:
                candidates.insert(0, (pid, 0.0))
                existing_pids.add(pid)

    if not candidates:
        log.info("No candidate projects found")
        return {"action": "no_candidates"}

    log.info("Found candidate projects", count=len(candidates))

    # Step 3: Update each candidate project's MEMORY.md
    results = {}
    for project_id, distance in candidates:
        t_update = time.monotonic()
        async with get_session_factory()() as session:
            result = await _update_project_memory_md(session, project_id, knowledge_text)
        update_elapsed = time.monotonic() - t_update
        results[str(project_id)] = result
        log.info(
            "Project MEMORY.md update result",
            project=str(project_id)[:8],
            result=result,
            elapsed=f"{update_elapsed:.2f}s",
            distance=f"{distance:.4f}",
        )

    return {"action": "completed", "results": results}


async def _extract_knowledge(
    conversation_text: str, summary_md: str, entity_anchors: str = ""
) -> str | None:
    """LLM 提取运维知识。返回 None 表示无可提取知识。"""
    log = get_logger(component="post_incident")
    input_text = f"## 排查过程\n{conversation_text[:6000]}\n\n## 排查结论\n{summary_md[:3000]}"

    system_prompt = EXTRACT_KNOWLEDGE_PROMPT.format(entity_anchors=entity_anchors)
    log.debug("Extract knowledge system prompt", prompt=system_prompt)
    log.info(
        "Calling LLM to extract knowledge",
        input_len=len(input_text),
        prompt_len=len(system_prompt),
    )
    llm = get_mini_llm()
    log.info("Calling LLM for knowledge extraction")
    try:
        resp = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=input_text),
            ]
        )
        log.info(
            "LLM responded for knowledge extraction",
            resp_content_type=type(resp.content).__name__,
            resp_len=len(resp.content) if resp.content else 0,
        )
    except Exception:
        log.error("LLM call failed for knowledge extraction", exc_info=True)
        raise
    result = resp.content.strip()
    if result == "NO_KNOWLEDGE" or len(result) < 20:
        log.info("LLM returned no extractable knowledge", result_len=len(result))
        log.debug("LLM returned no extractable knowledge", result=result)
        return None
    log.info("LLM extracted knowledge", chars=len(result))
    log.debug("Extracted knowledge", content=result)
    return result


async def _find_candidate_projects(knowledge_text: str) -> list[tuple[uuid.UUID, float]]:
    """向量搜索 DocumentChunk，按 project_id 分组取 top 项目。"""
    log = get_logger(component="post_incident")
    log.info("Starting vector search for candidate projects", text_len=len(knowledge_text))
    embedder = Embedder()
    embedding = await embedder.embed_text(knowledge_text)
    log.info("Embedding computed", dim=len(embedding))

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

    log.info("Vector search returned rows", count=len(rows))

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
    candidates = [(pid, dist) for pid, dist in best_by_project.items() if dist < 0.3]
    # Sort by distance ascending
    candidates.sort(key=lambda x: x[1])
    log.info(
        "Candidate projects after filtering",
        candidates=len(candidates),
        threshold=0.3,
        total_projects=len(best_by_project),
    )
    return candidates


async def _update_project_memory_md(
    session: AsyncSession,
    project_id: uuid.UUID,
    knowledge_text: str,
) -> str:
    """读取项目 MEMORY.md，LLM 判断并执行更新。
    返回 "updated" | "skipped" | "no_doc"
    """
    log = get_logger(component="post_incident")
    pid_short = str(project_id)[:8]
    log.info("Updating project MEMORY.md", project=pid_short, knowledge_len=len(knowledge_text))

    # Find the MEMORY.md document
    result = await session.execute(
        select(ProjectDocument)
        .where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.doc_type == "memory_config",
        )
        .limit(1)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        log.info("Project has no memory_config doc", project=pid_short)
        return "no_doc"

    current_content = doc.content or ""
    log.info(
        "Current MEMORY.md content loaded", project=pid_short, content_len=len(current_content)
    )

    # Ask LLM whether to update
    llm = get_mini_llm()
    prompt = SHOULD_UPDATE_PROMPT.format(
        current_content=current_content if current_content.strip() else "(空)",
        knowledge_text=knowledge_text,
    )
    log.info("Calling LLM for MEMORY.md update decision", prompt_len=len(prompt))
    try:
        resp = await llm.ainvoke(
            [
                HumanMessage(content=prompt),
            ]
        )
        resp_len = len(resp.content) if resp.content else 0
        resp_preview = repr(resp.content[:200]) if resp.content else "None"
        log.info(
            "LLM responded for MEMORY.md update",
            resp_len=resp_len,
            preview=resp_preview,
        )
    except Exception:
        log.error("LLM call failed for MEMORY.md update", exc_info=True)
        raise
    result_text = resp.content.strip()

    if result_text == "NO_UPDATE":
        log.info("LLM says NO_UPDATE", project=pid_short)
        return "skipped"

    # Remove outermost markdown code block wrapper if present
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*?)(?:\n```\s*)$", result_text, re.DOTALL)
    if m:
        result_text = m.group(1)

    # Update first, then save new content as version
    doc.content = result_text
    doc.status = "indexed"

    # Sync to disk
    from src.lib.paths import knowledge_dir

    project = await session.get(Project, project_id)
    if project:
        file_path = knowledge_dir(project.slug) / "MEMORY.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(result_text, encoding="utf-8")

    from src.services.version_service import VersionService

    vs = VersionService(session)
    await vs.save_version(
        entity_type="memory_md",
        entity_id=str(doc.id),
        content=result_text,
        change_source="auto",
    )
    await session.commit()
    log.info("Project MEMORY.md updated and committed", project=pid_short)
    return "updated"
