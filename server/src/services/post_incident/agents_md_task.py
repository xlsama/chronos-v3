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
from src.services.post_incident.base import get_main_llm

EXTRACT_KNOWLEDGE_PROMPT = """\
你是一个运维知识提取器。从以下事件排查过程中提取可复用的运维知识。

重点提取以下信息:

### 1. Server 与 Service 拓扑
从对话中识别出涉及的服务器(Server)和服务(Service)，提取它们的关系:
- Server 信息: 名称、IP/Host、用途
- Service 信息: 名称、类型(mysql/redis/nginx等)、端口、所在 Server
- **Service → Server 归属**: 哪个 Service 运行在哪个 Server 上
- **Service 间依赖关系**: 用 `A -->|关系描述| B` 格式描述依赖方向和类型，例如 `nginx -->|反向代理| app-backend`、`app-backend -->|数据存储| app-mysql`

### 2. 服务配置
- 端口、路径、配置文件位置
- 关键配置参数（仅限配置文件中的固定值，不包括从故障现象推断的参数）

### 3. 运维信息
- 部署方式（Docker Compose / K8s / 直接部署，镜像名、compose 文件路径）
- 日志路径（各服务的日志获取方式，如 docker logs、文件路径）
- 健康检查（各服务的健康检查端点和预期响应）

规则:
- 只提取**基础设施层面**的静态知识（即使没有事件发生也成立的信息）
- 不要一次性信息（如具体的时间戳、临时文件名）
- **严禁提取事件特定信息**，包括但不限于:
  - 故障的错误信息和异常日志特征（如 "Connection is not available"、"metadata lock"）
  - 排查关键词
  - 根因分析和故障恢复步骤
  - 从故障现象推断的配置值（如从超时报错推断的超时时间）
  这些信息属于事件历史，不属于运维手册
- Server/Service 名称要与系统中已配置的名称保持一致（如果对话中提到了）
{entity_anchors}
- 无可提取知识则只输出 "NO_KNOWLEDGE"
"""

SHOULD_UPDATE_PROMPT = """\
你是 AGENTS.md 文档维护助手。判断是否需要将新知识更新到 AGENTS.md。

## AGENTS.md 标准结构

AGENTS.md 应包含以下章节（按需填充，没有信息的章节不要创建）:

````markdown
# 项目运维手册

## 架构拓扑

### Servers
| Server 名称 | Host/IP | 用途 |
|---|---|---|
| prod-web-01 | 10.0.1.10 | Web 应用服务器 |
| prod-db-01 | 10.0.1.20 | 数据库服务器 |

### Services
| Service 名称 | 类型 | 所在 Server | 端口 | 说明 |
|---|---|---|---|---|
| nginx | Nginx | prod-web-01 | 80/443 | 反向代理 |
| app-backend | Java | prod-web-01 | 8080 | 核心 API |
| app-mysql | MySQL | prod-db-01 | 3306 | 主数据库 |

### 架构图

[根据上方 Services 表自动生成 Mermaid flowchart 拓扑图]

## 服务配置
[各服务的固定配置: 配置文件路径、端口、API 端点等。不包括从故障中推断的参数或运行时状态]

## 运维信息

### 部署方式
[Docker Compose / K8s / 直接部署，镜像名、compose 文件路径]

### 日志路径
| 服务 | 日志位置 | 说明 |
|---|---|---|
| app-backend | docker logs app-backend | 容器日志 |

### 健康检查
| 服务 | 端点 | 预期响应 |
|---|---|---|
| app-backend | GET :8080/actuator/health | {{"status":"UP"}} |

````

## 架构图规范

架构图使用 Mermaid flowchart 格式，注意以下关键约束：
- 必须使用 `flowchart TD`（从上到下）
- **不要使用 subgraph**，Server 归属写在节点标签内（用 `\n` 换行）
- **节点 ID 不能含空格或特殊字符**，使用短横线连接（如 `app-backend`、`app-mysql`），ID 必须与 Services 表中名称一致
- 节点标签应包含：服务名称、端口、所在 Server
- 根据服务类型选择合适的节点形状和 emoji 来区分不同角色（网关、应用、数据库、缓存等），具体语法由你自行决定
- 依赖关系用带标签箭头表示：`A -->|关系描述| B`
- 优先保证语法正确性，宁可使用简单的节点形状也不要生成无效语法

## 更新规则
1. 完全重复的内容 → 只输出 "NO_UPDATE"
2. 有价值的补充 → 输出更新后的完整 AGENTS.md 内容
3. **保持现有内容不变**，只增量补充新信息
4. 新发现的 Server/Service 关系要同步更新表格和架构图：新 Server → 加表格行，新 Service → 加表格行 + 架构图加节点，新依赖 → 加箭头
5. 若当前 AGENTS.md 为空，按上述标准结构创建初始内容
6. 不要编造信息，只写对话中实际出现的事实
7. **严格遵守标准结构**，只允许标准章节: 架构拓扑(Servers/Services/架构图)、服务配置、运维信息(部署方式/日志路径/健康检查)。禁止新增"排查关键词"、"异常状态监控"、"故障恢复指南"等事件衍生章节
8. **禁止写入事件特定内容**: 错误信息、故障模式、根因分析、修复步骤等属于事件历史，不属于运维手册。如果现有内容中包含此类信息，更新时应将其移除

## 当前 AGENTS.md 内容
```
{current_content}
```

## 新提取的运维知识
```
{knowledge_text}
```

如果无需更新只输出 "NO_UPDATE"，否则输出更新后的完整 AGENTS.md 内容（纯 Markdown，不要用代码块包裹）。"""


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


async def auto_update_agents_md(
    incident_id: str,
    summary_md: str,
    conversation_text: str,
    kb_project_ids: list[str] | None = None,
) -> dict:
    """主入口。向量搜索匹配项目，KB Agent 已匹配的项目作为必选候选。"""
    sid = incident_id[:8]
    log = get_logger(component="post_incident", sid=sid)
    log.info("Starting AGENTS.md auto-update")

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

    # Step 3: Update each candidate project's AGENTS.md
    results = {}
    for project_id, distance in candidates:
        t_update = time.monotonic()
        async with get_session_factory()() as session:
            result = await _update_project_agents_md(session, project_id, knowledge_text)
        update_elapsed = time.monotonic() - t_update
        results[str(project_id)] = result
        log.info(
            "Project AGENTS.md update result",
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
    llm = get_main_llm()
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


async def _update_project_agents_md(
    session: AsyncSession,
    project_id: uuid.UUID,
    knowledge_text: str,
) -> str:
    """读取项目 AGENTS.md，LLM 判断并执行更新。
    返回 "updated" | "skipped" | "no_doc"
    """
    log = get_logger(component="post_incident")
    pid_short = str(project_id)[:8]
    log.info("Updating project AGENTS.md", project=pid_short, knowledge_len=len(knowledge_text))

    # Find the AGENTS.md document
    result = await session.execute(
        select(ProjectDocument)
        .where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.doc_type == "agents_config",
        )
        .limit(1)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        log.info("Project has no agents_config doc", project=pid_short)
        return "no_doc"

    current_content = doc.content or ""
    log.info(
        "Current AGENTS.md content loaded", project=pid_short, content_len=len(current_content)
    )

    # Ask LLM whether to update
    llm = get_main_llm()
    prompt = SHOULD_UPDATE_PROMPT.format(
        current_content=current_content if current_content.strip() else "(空)",
        knowledge_text=knowledge_text,
    )
    log.info("Calling LLM for AGENTS.md update decision", prompt_len=len(prompt))
    try:
        resp = await llm.ainvoke(
            [
                HumanMessage(content=prompt),
            ]
        )
        resp_len = len(resp.content) if resp.content else 0
        resp_preview = repr(resp.content[:200]) if resp.content else "None"
        log.info(
            "LLM responded for AGENTS.md update",
            resp_len=resp_len,
            preview=resp_preview,
        )
    except Exception:
        log.error("LLM call failed for AGENTS.md update", exc_info=True)
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
        file_path = knowledge_dir(project.slug) / "AGENTS.md"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(result_text, encoding="utf-8")

    from src.services.version_service import VersionService

    vs = VersionService(session)
    await vs.save_version(
        entity_type="agents_md",
        entity_id=str(doc.id),
        content=result_text,
        change_source="auto",
    )
    await session.commit()
    log.info("Project AGENTS.md updated and committed", project=pid_short)
    return "updated"
