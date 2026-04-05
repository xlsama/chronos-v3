"""定时任务: 批量分析历史事件和项目架构，自动进化 skill。"""

import json
import re
import time
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from src.db.connection import get_session_factory
from src.db.models import IncidentHistory
from src.lib.logger import get_logger
from src.services.post_incident.base import get_mini_llm
from src.services.skill_service import SkillService
from src.services.version_service import VersionService

log = get_logger(component="cron")

# ── Phase 1: 跨事件模式分析 ──────────────────────────────────

_CROSS_INCIDENT_ANALYSIS_PROMPT = """\
你是一个运维知识架构师。分析以下所有历史事件和项目架构，识别跨事件的共性排查模式。

要求:
1. 寻找多个事件中反复出现的排查链路和修复方式
2. 关注共性，忽略一次性的特殊情况
3. 结合项目架构理解基础设施上下文
4. 输出通用技能（不针对特定项目）

输出格式（JSON 数组）:
[
  {{
    "name": "技能名称",
    "description": "一句话描述技能做什么",
    "when_to_use": "什么场景使用此技能。格式：当 X 时使用。不适用于 Y。",
    "pattern": "pipeline|tool-wrapper|inversion",
    "domain": "可选领域标签，如 database/network/docker/kubernetes/jvm",
    "tags": ["标签1", "标签2"],
    "related_services": ["服务类型1", "服务类型2"],
    "rationale": "为什么这是一个通用模式（引用了哪些事件）",
    "outline": "排查步骤大纲（简明列出关键步骤）"
  }}
]

如果没有发现有价值的跨事件模式，返回空数组 []。
只输出 JSON，不要输出其他内容。

=== 历史事件 ===
{incidents_text}

=== 项目架构 ===
{memory_text}
"""

# ── Phase 2: 匹配 & 生成 ──────────────────────────────────

_MATCH_PROMPT = """\
你是一个运维知识管理专家。判断以下新提取的排查流程是否与某个现有技能重叠。

新流程摘要:
名称: {new_name}
描述: {new_description}

现有技能列表:
{skills_list}

如果新流程与某个现有技能高度重叠，回复: MATCH:<slug>
如果新流程是全新的，回复: NEW:<suggested-slug>

slug 格式: 小写字母+数字+连字符，如 mysql-oom, redis-latency
只回复一行，不要解释。"""

_GENERATE_SKILL_PROMPT = """\
你是一个运维知识架构师。根据以下模式分析结果，生成一个完整的 SKILL.md 文件。

模式信息:
- 名称: {name}
- 描述: {description}
- 触发条件: {when_to_use}
- 类型: {pattern}
- 领域: {domain}
- 标签: {tags}
- 关联服务: {related_services}
- 依据: {rationale}
- 步骤大纲: {outline}

根据模式类型，使用对应模板生成完整的 SKILL.md。

**Frontmatter 必须包含以下字段：**
- name: 技能名称
- description: 一句话描述技能做什么（WHAT）
- when_to_use: 什么场景使用。格式："当 X 时使用。不适用于 Y。"
- tags: 领域标签列表
- related_services: 关联的服务类型列表
- draft: true

### Pipeline 模式:
```
---
name: <技能名称>
description: <一句话描述>
when_to_use: <触发条件和排除条件>
tags: [标签列表]
related_services: [服务类型列表]
draft: true
metadata:
  pattern: pipeline
  source: cron
  generated_at: "{generated_at}"
  domain: <领域>
  steps: "<步骤数>"
---

## 适用场景
当 <触发条件> 时使用此技能。
不适用于 <排除条件>。

## Step 1 — <步骤标题>
<命令和判断标准>
**验证标准**: <如何确认此步完成>

## Step 2 — <步骤标题>
<命令和判断标准>
**验证标准**: <如何确认此步完成>

## 升级条件
当 <条件> 时需要人工介入。
```

### Tool Wrapper 模式:
```
---
name: <技能名称>
description: <一句话描述>
when_to_use: <触发条件和排除条件>
tags: [标签列表]
related_services: [服务类型列表]
draft: true
metadata:
  pattern: tool-wrapper
  source: cron
  generated_at: "{generated_at}"
  domain: <技术领域>
---

## 适用场景
当 <触发条件> 时使用此技能。

## 核心规范
<关键规则和检查项>

## 排查步骤
### Step 1 — <步骤>
<操作>
**验证标准**: <完成标志>
```

### Inversion 模式:
```
---
name: <技能名称>
description: <一句话描述>
when_to_use: <触发条件和排除条件>
tags: [标签列表]
related_services: [服务类型列表]
draft: true
metadata:
  pattern: inversion
  source: cron
  generated_at: "{generated_at}"
  domain: <领域>
---

## 适用场景
当 <触发条件> 时使用此技能。

## Phase 1 — 信息收集
- Q1: "<问题>"
- Q2: "<问题>"

## Phase 2 — 执行排查
基于收集的信息选择合适的排查路径。

## 升级条件
当 <条件> 时需要人工介入。
```

注意:
- draft: true 必须保留
- metadata.source 必须为 cron
- 每个步骤必须包含 **验证标准**（借鉴 Claude Code 的 Success Criteria 模式）
- 包含 **升级条件** 段，明确何时需要人工介入
- 内容要具体、可操作，包含实际的命令和判断标准
- 只输出 SKILL.md 内容，不要输出其他说明"""

_MERGE_PROMPT = """\
你是一个运维知识管理专家。将新的排查经验合并到现有技能中。

现有技能内容:
```
{existing_content}
```

新的排查经验:
名称: {new_name}
描述: {new_description}
步骤大纲: {outline}

要求:
1. 保留现有技能的结构和核心内容
2. 将新经验中有价值的信息补充到合适的位置
3. 避免重复
4. 确保 frontmatter 中 draft: true
5. 如果新经验没有提供额外有价值的信息，回复 NO_UPDATE
6. 如果需要更新，输出完整的更新后 SKILL.md 内容（包含 frontmatter）"""

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _clean_code_block(text: str) -> str:
    """去除 LLM 输出中的代码块标记。"""
    content = text.strip().strip("`").strip()
    if content.startswith("markdown\n"):
        content = content[len("markdown\n") :]
    if content.startswith("```\n"):
        content = content[4:]
    if content.endswith("\n```"):
        content = content[:-4]
    return content


def _ensure_draft(content: str) -> str:
    """确保 SKILL.md 内容包含 draft: true。"""
    if "draft: true" not in content:
        content = content.replace("---\n", "---\ndraft: true\n", 1)
    return content


def _build_analysis_input(
    incidents: list[IncidentHistory], memory_docs: list[dict]
) -> tuple[str, str]:
    """拼接事件和架构文本，直接全量传给 LLM。"""
    incident_parts = []
    for inc in incidents:
        incident_parts.append(
            f"### [{inc.title}] (出现 {inc.occurrence_count} 次)\n{inc.summary_md}"
        )
    incidents_text = "\n\n".join(incident_parts) if incident_parts else "（无近期事件）"

    memory_parts = []
    for doc in memory_docs:
        memory_parts.append(f"### 项目: {doc['project_name']}\n{doc['content']}")
    memory_text = "\n\n".join(memory_parts) if memory_parts else "（无项目架构信息）"

    return incidents_text, memory_text


# ── Phase 1: 分析 ──────────────────────────────────────────


async def _analyze_patterns(incidents_text: str, memory_text: str) -> list[dict]:
    """Phase 1: LLM 分析跨事件共性模式，返回模式候选列表。"""
    llm = get_mini_llm()
    prompt = _CROSS_INCIDENT_ANALYSIS_PROMPT.format(
        incidents_text=incidents_text,
        memory_text=memory_text,
    )
    log.info("Phase 1: analyzing cross-incident patterns", prompt_len=len(prompt))
    t0 = time.monotonic()

    resp = await llm.ainvoke(
        [
            SystemMessage(content="你是一个运维知识架构师，擅长从多个事件中归纳通用排查模式。"),
            HumanMessage(content=prompt),
        ]
    )

    elapsed = time.monotonic() - t0
    raw = resp.content.strip()
    log.info("Phase 1: LLM responded", elapsed=f"{elapsed:.2f}s", resp_len=len(raw))

    # 解析 JSON
    try:
        # 处理可能被代码块包裹的 JSON
        cleaned = _clean_code_block(raw)
        if cleaned.startswith("json\n"):
            cleaned = cleaned[len("json\n") :]
        patterns = json.loads(cleaned)
        if not isinstance(patterns, list):
            log.warning("Phase 1: LLM returned non-list", type=type(patterns).__name__)
            return []
        log.info("Phase 1: patterns identified", count=len(patterns))
        return patterns
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("Phase 1: failed to parse LLM response", error=str(e), raw=raw[:200])
        return []


# ── Phase 2: 匹配 + 生成/合并 ────────────────────────────────


async def _process_pattern_candidates(patterns: list[dict]) -> list[str]:
    """Phase 2: 逐个处理模式候选，匹配/创建/合并 skill。"""
    llm = get_mini_llm()
    service = SkillService()
    results = []

    all_skills = service.list_skills()
    skills_list = (
        "\n".join(f"- {s.slug}: {s.name} — {s.description}" for s in all_skills)
        or "（暂无现有技能）"
    )

    now_iso = datetime.now(timezone.utc).isoformat()

    for i, pattern in enumerate(patterns):
        name = pattern.get("name", "")
        description = pattern.get("description", "")
        when_to_use = pattern.get("when_to_use", "")
        pat_type = pattern.get("pattern", "pipeline")
        domain = pattern.get("domain", "")
        tags = pattern.get("tags", [])
        related_services = pattern.get("related_services", [])
        rationale = pattern.get("rationale", "")
        outline = pattern.get("outline", "")

        if not name or not description:
            log.warning("Phase 2: skipping pattern with missing name/description", index=i)
            continue

        log.info("Phase 2: processing pattern", index=i, name=name, pattern=pat_type)

        try:
            result = await _match_and_apply(
                llm,
                service,
                skills_list,
                name,
                description,
                when_to_use,
                pat_type,
                domain,
                tags,
                related_services,
                rationale,
                outline,
                now_iso,
            )
            results.append(result)
            log.info("Phase 2: pattern processed", index=i, result=result)
        except Exception:
            log.error("Phase 2: failed to process pattern", index=i, name=name, exc_info=True)
            results.append(f"error: {name}")

    return results


async def _match_and_apply(
    llm,
    service: SkillService,
    skills_list: str,
    name: str,
    description: str,
    when_to_use: str,
    pattern: str,
    domain: str,
    tags: list[str],
    related_services: list[str],
    rationale: str,
    outline: str,
    now_iso: str,
) -> str:
    """对单个模式候选执行匹配 → 合并或创建。"""
    # Step 1: 匹配现有 skill
    match_prompt = _MATCH_PROMPT.format(
        new_name=name,
        new_description=description,
        skills_list=skills_list,
    )
    match_resp = await llm.ainvoke(match_prompt)
    match_result = match_resp.content.strip()
    log.info("Match result", name=name, result=match_result)

    if match_result.startswith("MATCH:"):
        return await _merge_skill(
            llm,
            service,
            match_result,
            name,
            description,
            outline,
        )
    elif match_result.startswith("NEW:"):
        return await _create_skill(
            llm,
            service,
            match_result,
            name,
            description,
            when_to_use,
            pattern,
            domain,
            tags,
            related_services,
            rationale,
            outline,
            now_iso,
        )
    else:
        log.warning("Unexpected match result", name=name, result=match_result)
        return f"skipped: unexpected match for '{name}'"


async def _merge_skill(
    llm,
    service: SkillService,
    match_result: str,
    name: str,
    description: str,
    outline: str,
) -> str:
    """合并到已有 skill。"""
    slug = match_result.removeprefix("MATCH:").strip()
    try:
        meta, existing_raw = service.get_skill(slug)
    except FileNotFoundError:
        log.warning("Matched skill not found", slug=slug)
        return f"skipped: matched skill '{slug}' not found"

    merge_prompt = _MERGE_PROMPT.format(
        existing_content=existing_raw,
        new_name=name,
        new_description=description,
        outline=outline,
    )
    merge_resp = await llm.ainvoke(merge_prompt)
    merged = merge_resp.content.strip()

    if "NO_UPDATE" in merged:
        log.info("No update needed for skill", slug=slug)
        return f"skipped: no update for '{slug}'"

    merged_content = _ensure_draft(_clean_code_block(merged))

    service.update_skill(slug, merged_content)

    async with get_session_factory()() as session:
        vs = VersionService(session)
        await vs.save_version(
            entity_type="skill",
            entity_id=slug,
            content=merged_content,
            change_source="cron",
        )
        await session.commit()

    log.info("Updated existing skill", slug=slug)
    return f"updated: {slug}"


async def _create_skill(
    llm,
    service: SkillService,
    match_result: str,
    name: str,
    description: str,
    when_to_use: str,
    pattern: str,
    domain: str,
    tags: list[str],
    related_services: list[str],
    rationale: str,
    outline: str,
    now_iso: str,
) -> str:
    """创建新 skill (draft)。"""
    slug = match_result.removeprefix("NEW:").strip()

    if not _SLUG_RE.match(slug) or len(slug) > 64:
        slug = "auto-" + uuid.uuid4().hex[:8]

    # 生成完整 SKILL.md
    gen_prompt = _GENERATE_SKILL_PROMPT.format(
        name=name,
        description=description,
        when_to_use=when_to_use or f"当涉及{name}相关问题时使用",
        pattern=pattern,
        domain=domain or "通用",
        tags=", ".join(tags) if tags else domain or "通用",
        related_services=", ".join(related_services) if related_services else "无",
        rationale=rationale,
        outline=outline,
        generated_at=now_iso,
    )
    gen_resp = await llm.ainvoke(gen_prompt)
    content = _ensure_draft(_clean_code_block(gen_resp.content.strip()))

    # 创建 skill 目录
    try:
        service.create_skill(slug)
    except FileExistsError:
        slug = f"{slug}-{uuid.uuid4().hex[:8]}"
        try:
            service.create_skill(slug)
        except FileExistsError:
            return f"skipped: could not create skill '{slug}'"

    service.update_skill(slug, content)

    async with get_session_factory()() as session:
        vs = VersionService(session)
        await vs.save_version(
            entity_type="skill",
            entity_id=slug,
            content=content,
            change_source="cron",
        )
        await session.commit()

    log.info("Created new draft skill", slug=slug)
    return f"created: {slug} (draft)"


# ── 入口 ────────────────────────────────────────────────


async def run_skill_evolution_job(
    incidents: list[IncidentHistory],
    memory_docs: list[dict],
) -> None:
    """定时任务入口: 批量分析历史事件，自动进化 skill。

    Args:
        incidents: 近 24h 的 IncidentHistory 列表
        memory_docs: 所有项目的 MEMORY.md，每项含 project_id, project_name, project_slug, content
    """
    log.info("=== Skill Evolution Job Started ===")
    t_start = time.monotonic()

    try:
        if not incidents:
            log.info("No recent incidents, skipping skill evolution")
            return

        # 1. 构建分析输入
        incidents_text, memory_text = _build_analysis_input(incidents, memory_docs)

        # 2. Phase 1: 跨事件模式分析
        patterns = await _analyze_patterns(incidents_text, memory_text)
        if not patterns:
            log.info("No cross-incident patterns identified, done")
            return

        # 3. Phase 2: 匹配 + 生成/合并
        results = await _process_pattern_candidates(patterns)

        elapsed = time.monotonic() - t_start
        log.info(
            "=== Skill Evolution Job Completed ===",
            elapsed=f"{elapsed:.2f}s",
            patterns_found=len(patterns),
            results=results,
        )
    except Exception:
        log.error("Skill Evolution Job failed", exc_info=True)
