import re
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_session_factory
from src.db.models import DocumentChunk, ProjectDocument
from src.lib.embedder import Embedder
from src.lib.logger import logger
from src.services.post_incident.base import get_mini_llm

EXTRACT_KNOWLEDGE_PROMPT = """\
你是一个运维知识提取器。从以下事件排查过程中提取可复用的运维知识。

重点提取以下信息:

### 1. Server 与 Service 拓扑
从对话中识别出涉及的服务器(Server)和服务(Service)，提取它们的关系:
- Server 信息: 名称、IP/Host、用途
- Service 信息: 名称、类型(mysql/redis/nginx等)、端口、所在 Server
- **Service → Server 归属**: 哪个 Service 运行在哪个 Server 上（用于 Mermaid subgraph 分组）
- **Service 间依赖关系**: 用 `A -->|关系描述| B` 格式描述依赖方向和类型，例如 `nginx -->|反向代理| app-backend`、`app-backend -->|数据存储| app-mysql`

### 2. 服务配置
- 端口、路径、配置文件位置
- 关键配置参数

### 3. 排查经验
- 排查方法论（如何定位此类问题）
- 关键发现/陷阱（容易踩坑的地方）
- 修复方案

规则:
- 只提取事实性的、可复用的知识
- 不要一次性信息（如具体的时间戳、临时文件名）
- Server/Service 名称要与系统中已配置的名称保持一致（如果对话中提到了）
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

```mermaid
flowchart LR
  subgraph prod-web-01["prod-web-01 (10.0.1.10)"]
    nginx["nginx :80/443"]
    app-backend["app-backend :8080"]
  end
  subgraph prod-db-01["prod-db-01 (10.0.1.20)"]
    app-mysql["app-mysql :3306"]
  end
  nginx -->|反向代理| app-backend
  app-backend -->|数据存储| app-mysql
```

## 服务配置
[各服务的关键配置信息: 配置文件路径、重要参数等]

## 排查经验
[历次排查积累的经验和注意事项]
````

## 架构图规范

架构图使用 Mermaid flowchart 格式，遵循以下规则：
- 类型：`flowchart LR`（左到右，符合请求流向）
- **Server** → `subgraph`，ID 为 Server 名称，标签格式 `"Server名 (IP)"`
- **Service** → subgraph 内节点，ID 为 Service 名称，标签格式 `"Service名 :端口"`
- **依赖关系** → 带标签箭头 `serviceA -->|关系描述| serviceB`
- **外部服务** → `subgraph external["外部服务"]`
- 节点 ID 必须与 Services 表中的名称一致

## 更新规则
1. 完全重复的内容 → 只输出 "NO_UPDATE"
2. 有价值的补充 → 输出更新后的完整 AGENTS.md 内容
3. **保持现有内容不变**，只增量补充新信息
4. 新发现的 Server/Service 关系要同步更新表格和架构图：新 Server → 加表格行 + 加 subgraph，新 Service → 加表格行 + 加节点，新依赖 → 加箭头
5. 若当前 AGENTS.md 为空，按上述标准结构创建初始内容
6. 不要编造信息，只写对话中实际出现的事实

## 当前 AGENTS.md 内容
```
{current_content}
```

## 新提取的运维知识
```
{knowledge_text}
```

如果无需更新只输出 "NO_UPDATE"，否则输出更新后的完整 AGENTS.md 内容（纯 Markdown，不要用代码块包裹）。"""


async def auto_update_agents_md(
    incident_id: str,
    summary_md: str,
    conversation_text: str,
) -> dict:
    """主入口。纯向量搜索匹配项目，不依赖 incident 的 project_id。"""
    sid = incident_id[:8]
    logger.info(f"[{sid}] [agents_md] Starting AGENTS.md auto-update")

    # Step 1: Extract operational knowledge
    knowledge_text = await _extract_knowledge(conversation_text, summary_md)
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


async def _extract_knowledge(conversation_text: str, summary_md: str) -> str | None:
    """LLM 提取运维知识。返回 None 表示无可提取知识。"""
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

    # Remove outermost markdown code block wrapper if present
    m = re.match(r'^```(?:markdown|md)?\s*\n(.*?)(?:\n```\s*)$', result_text, re.DOTALL)
    if m:
        result_text = m.group(1)

    # Update first, then save new content as version
    doc.content = result_text
    doc.status = "indexed"

    from src.services.version_service import VersionService
    vs = VersionService(session)
    await vs.save_version(
        entity_type="agents_md", entity_id=str(doc.id),
        content=result_text, change_source="auto",
    )
    await session.commit()
    return "updated"
