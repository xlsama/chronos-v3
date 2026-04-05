"""定时任务: 批量分析历史事件，更新所有项目的 MEMORY.md。"""

import time

from langchain_core.messages import HumanMessage, SystemMessage

from src.db.connection import get_session_factory
from src.db.models import IncidentHistory
from src.lib.logger import get_logger
from src.services.post_incident.memory_md_task import (
    _fetch_entity_anchors,
    _update_project_memory_md,
)
from src.services.post_incident.base import get_mini_llm

log = get_logger(component="cron")

# ── Prompt ──────────────────────────────────────────────────

_BATCH_EXTRACT_KNOWLEDGE_PROMPT = """\
你是运维知识提取器。从多个历史事件的排查报告中提取与指定项目相关的可复用运维知识。

目标项目: {project_name}

项目当前 MEMORY.md 内容:
```
{current_memory_md}
```

{entity_anchors}

## 近期历史事件

{incidents_text}

## 提取要求

重点提取与目标项目相关的:
1. **Server 与 Service 拓扑**: 名称、IP/Host、类型、端口、归属关系、依赖关系
2. **服务配置**: 端口、路径、配置文件位置（仅固定值，不含故障推断值）
3. **运维信息**: 部署方式、日志路径、健康检查端点
4. **跨事件洞察**: 多个事件共同揭示的架构关系或基础设施依赖

规则:
- 只提取基础设施层面的静态知识（即使没有事件也成立的信息）
- 综合多个事件交叉验证，提取单个事件可能遗漏的关联信息
- 不要一次性信息（时间戳、临时文件名）
- **严禁提取事件特定信息**: 错误信息、异常日志特征、排查关键词、根因分析、故障恢复步骤
- 不要提取 MEMORY.md 中已有的信息（避免重复）
- Server/Service 名称与系统中已配置的保持一致
- 无可提取知识则只输出 "NO_KNOWLEDGE"
"""


# ── 辅助函数 ────────────────────────────────────────────────


def _build_incidents_text(incidents: list[IncidentHistory]) -> str:
    """将多条 IncidentHistory 拼接为 LLM 可读文本。"""
    parts = []
    for inc in incidents:
        parts.append(f"### [{inc.title}] (出现 {inc.occurrence_count} 次)\n{inc.summary_md}")
    return "\n\n".join(parts) if parts else "（无近期事件）"


async def _extract_batch_knowledge(
    incidents_text: str,
    project_name: str,
    current_memory_md: str,
    entity_anchors: str,
) -> str | None:
    """LLM 从多个历史事件中提取与指定项目相关的基础设施知识。

    Returns:
        提取的知识文本，或 None 表示无可提取知识。
    """
    prompt = _BATCH_EXTRACT_KNOWLEDGE_PROMPT.format(
        project_name=project_name,
        current_memory_md=current_memory_md if current_memory_md.strip() else "(空)",
        entity_anchors=entity_anchors,
        incidents_text=incidents_text,
    )

    llm = get_mini_llm()
    resp = await llm.ainvoke(
        [
            SystemMessage(
                content="你是一个运维知识提取器，擅长从多个事件报告中归纳项目相关的基础设施知识。"
            ),
            HumanMessage(content=prompt),
        ]
    )

    result = resp.content.strip()
    if result == "NO_KNOWLEDGE" or len(result) < 20:
        return None
    return result


# ── 入口 ────────────────────────────────────────────────────


async def run_memory_md_evolution_job(
    incidents: list[IncidentHistory],
    memory_docs: list[dict],
) -> None:
    """定时任务入口: 批量更新所有项目的 MEMORY.md。

    Args:
        incidents: 近 24h 的 IncidentHistory 列表
        memory_docs: 所有项目的 MEMORY.md，每项含 project_id, project_name, project_slug, content
    """
    log.info("=== MEMORY.md Evolution Job Started ===")
    t_start = time.monotonic()

    if not incidents:
        log.info("No recent incidents, skipping MEMORY.md evolution")
        return

    if not memory_docs:
        log.info("No projects with MEMORY.md, skipping")
        return

    # 1. 获取 entity anchors
    async with get_session_factory()() as session:
        entity_anchors = await _fetch_entity_anchors(session)

    # 2. 拼接历史事件文本
    incidents_text = _build_incidents_text(incidents)

    # 3. 遍历每个项目，提取知识并更新
    results: dict[str, str] = {}
    for doc in memory_docs:
        project_id = doc["project_id"]
        project_name = doc["project_name"]
        current_content = doc["content"] or ""
        pid_short = str(project_id)[:8]

        log.info("Processing project", project=project_name, pid=pid_short)
        t_proj = time.monotonic()

        # 3a. 提取知识
        knowledge_text = await _extract_batch_knowledge(
            incidents_text,
            project_name,
            current_content,
            entity_anchors,
        )
        if not knowledge_text:
            results[project_name] = "no_knowledge"
            log.info("No knowledge extracted for project", project=project_name)
            continue

        log.info(
            "Knowledge extracted for project",
            project=project_name,
            chars=len(knowledge_text),
        )

        # 3b. 更新 MEMORY.md（复用 post_incident 的更新逻辑）
        async with get_session_factory()() as session:
            result = await _update_project_memory_md(session, project_id, knowledge_text)

        results[project_name] = result
        proj_elapsed = time.monotonic() - t_proj
        log.info(
            "Project processed",
            project=project_name,
            result=result,
            elapsed=f"{proj_elapsed:.2f}s",
        )

    elapsed = time.monotonic() - t_start
    log.info(
        "=== MEMORY.md Evolution Job Completed ===",
        elapsed=f"{elapsed:.2f}s",
        projects_processed=len(results),
        results=results,
    )
