"""Skill 自进化: 事件后自动提取可复用排查流程，创建或更新 skill。"""

import time

from src.lib.logger import get_logger
from src.services.post_incident.base import get_mini_llm
from src.services.skill_service import SkillService

_EXTRACT_PROMPT = """你是一个运维知识提取专家。分析以下事件排查对话，判断是否包含可复用的标准化排查流程。

要求:
1. 只提取具有通用价值的排查流程（不是一次性操作）
2. 流程应包含: 问题识别、排查步骤、关键命令、判断标准
3. 如果对话没有可复用的排查流程，直接回复 NO_PROCEDURE

如果有可复用流程，先判断它属于哪种 pattern，然后按对应模式生成 SKILL.md:

### Pattern 类型:
- **pipeline**: 严格多步排查流程。特征: 有明确的步骤顺序（Step 1/2/3），每步有命令和判断标准。这是最常见的模式。
- **tool-wrapper**: 技术专家/知识库模式。特征: 提供某技术的规范和最佳实践，排查时对照规范检查。
- **inversion**: 信息收集模式。特征: 需要先向用户提问收集信息，再决定排查方向。适用于描述模糊的事件。

### Pipeline 模式模板:
```
---
name: <技能名称>
description: <一句话描述 WHAT 和 WHEN>
draft: true
metadata:
  pattern: pipeline
  steps: "<步骤数>"
---

按以下步骤严格顺序执行。每步完成后总结发现，再进入下一步。

## Step 1 — <步骤标题>
<命令和判断标准>

## Step 2 — <步骤标题>
<命令和判断标准>
```

### Tool Wrapper 模式模板:
```
---
name: <技能名称>
description: <一句话描述 WHAT 和 WHEN>
draft: true
metadata:
  pattern: tool-wrapper
  domain: <技术领域>
---

你是 <技术> 专家。应用以下规范排查用户的问题。

## 核心规范
<关键规则和检查项>

## 排查时
<按规范检查的步骤>
```

### Inversion 模式模板:
```
---
name: <技能名称>
description: <一句话描述 WHAT 和 WHEN>
draft: true
metadata:
  pattern: inversion
---

在开始排查前，你需要收集关键信息。按以下阶段逐一提问，每次只问一个问题。

## Phase 1 — <阶段标题>
- Q1: "<问题>"
- Q2: "<问题>"

## Phase 2 — 执行排查
基于收集的信息选择合适的排查路径。
```

注意:
- name 简洁有力，如 "MySQL OOM 排查"
- description 说明这个技能解决什么问题，什么时候用
- 大多数排查流程属于 pipeline 模式
- draft: true 表示需要人工审核

事件对话:
{conversation}
"""

_MATCH_PROMPT = """你是一个运维知识管理专家。判断以下新提取的排查流程是否与某个现有技能重叠。

新流程摘要:
名称: {new_name}
描述: {new_description}

现有技能列表:
{skills_list}

如果新流程与某个现有技能高度重叠，回复: MATCH:<slug>
如果新流程是全新的，回复: NEW:<suggested-slug>

slug 格式: 小写字母+数字+连字符，如 mysql-oom, redis-latency
只回复一行，不要解释。
"""

_MERGE_PROMPT = """你是一个运维知识管理专家。将新的排查经验合并到现有技能中。

现有技能内容:
```
{existing_content}
```

新的排查经验:
```
{new_content}
```

要求:
1. 保留现有技能的结构和核心内容
2. 将新经验中有价值的信息补充到合适的位置
3. 避免重复
4. 如果新经验没有提供额外有价值的信息，回复 NO_UPDATE
5. 如果需要更新，输出完整的更新后 SKILL.md 内容（包含 frontmatter）
"""


async def auto_evolve_skills(
    incident_id: str,
    summary_md: str,
    conversation_text: str,
) -> str:
    """自动提取排查流程并创建/更新 skill。返回操作描述。"""
    sid = incident_id[:8]
    log = get_logger(component="post_incident", sid=sid)
    log.info(
        "auto_evolve_skills called",
        summary_md_len=len(summary_md) if summary_md else 0,
        conversation_text_len=len(conversation_text) if conversation_text else 0,
    )

    if not summary_md or not conversation_text:
        return "skipped: no summary or conversation"

    llm = get_mini_llm()
    service = SkillService()

    # Step 1: 提取可复用排查流程
    conversation = conversation_text
    extract_prompt = _EXTRACT_PROMPT.format(conversation=conversation)
    log.info("Step 1: calling LLM to extract procedure", prompt_len=len(extract_prompt))
    t_step1 = time.monotonic()
    try:
        extract_resp = await llm.ainvoke(extract_prompt)
        step1_elapsed = time.monotonic() - t_step1
        log.info(
            "Step 1: LLM responded",
            elapsed=f"{step1_elapsed:.2f}s",
            resp_len=len(extract_resp.content),
            preview=extract_resp.content[:200],
        )
    except Exception:
        log.error("Step 1: LLM call failed", exc_info=True)
        raise
    extracted = extract_resp.content.strip()

    if "NO_PROCEDURE" in extracted:
        log.info("No reusable procedure found")
        return "skipped: no reusable procedure"

    # 解析提取的内容
    # 去除可能的代码块标记
    content = extracted.strip("`").strip()
    if content.startswith("markdown\n"):
        content = content[len("markdown\n") :]
    if content.startswith("```\n"):
        content = content[4:]
    if content.endswith("\n```"):
        content = content[:-4]

    # 从 frontmatter 提取 name 和 description
    new_name = ""
    new_description = ""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import yaml

            fm = yaml.safe_load(parts[1]) or {}
            new_name = fm.get("name", "")
            new_description = fm.get("description", "")

    if not new_name:
        log.warning("Could not extract name from procedure")
        return "skipped: invalid extracted content"

    log.info("Extracted procedure", name=new_name, description=new_description)

    # Step 2: 与现有 skills 匹配
    all_skills = service.list_skills()  # 包含 draft
    skills_list = (
        "\n".join(f"- {s.slug}: {s.name} — {s.description}" for s in all_skills)
        or "（暂无现有技能）"
    )

    match_prompt = _MATCH_PROMPT.format(
        new_name=new_name,
        new_description=new_description,
        skills_list=skills_list,
    )
    log.info(
        "Step 2: calling LLM to match skills",
        prompt_len=len(match_prompt),
        existing_skills=len(all_skills),
    )
    t_step2 = time.monotonic()
    try:
        match_resp = await llm.ainvoke(match_prompt)
        step2_elapsed = time.monotonic() - t_step2
        log.info(
            "Step 2: LLM responded",
            elapsed=f"{step2_elapsed:.2f}s",
            resp_len=len(match_resp.content),
            preview=match_resp.content[:200],
        )
    except Exception:
        log.error("Step 2: LLM call failed", exc_info=True)
        raise
    match_result = match_resp.content.strip()
    log.info("Match result", result=match_result)

    if match_result.startswith("MATCH:"):
        # Step 3: 合并到现有 skill
        slug = match_result.removeprefix("MATCH:").strip()
        try:
            meta, existing_raw = service.get_skill(slug)
        except FileNotFoundError:
            log.warning("Matched skill not found", slug=slug)
            return f"skipped: matched skill '{slug}' not found"

        merge_prompt = _MERGE_PROMPT.format(
            existing_content=existing_raw,
            new_content=content,
        )
        log.info("Step 3: calling LLM to merge", slug=slug, prompt_len=len(merge_prompt))
        t_step3 = time.monotonic()
        try:
            merge_resp = await llm.ainvoke(merge_prompt)
            step3_elapsed = time.monotonic() - t_step3
            log.info(
                "Step 3: LLM responded",
                elapsed=f"{step3_elapsed:.2f}s",
                resp_len=len(merge_resp.content),
                preview=merge_resp.content[:200],
            )
        except Exception:
            log.error("Step 3: LLM merge call failed", exc_info=True)
            raise
        merged = merge_resp.content.strip()

        if "NO_UPDATE" in merged:
            log.info("No update needed for skill", slug=slug)
            return f"skipped: no update needed for '{slug}'"

        # Clean up merged content
        merged_content = merged.strip("`").strip()
        if merged_content.startswith("markdown\n"):
            merged_content = merged_content[len("markdown\n") :]
        if merged_content.startswith("```\n"):
            merged_content = merged_content[4:]
        if merged_content.endswith("\n```"):
            merged_content = merged_content[:-4]

        # Update first, then save new content as version
        log.info("Updating existing skill", slug=slug, content_len=len(merged_content))
        service.update_skill(slug, merged_content)

        from src.db.connection import get_session_factory
        from src.services.version_service import VersionService

        async with get_session_factory()() as vs_session:
            vs = VersionService(vs_session)
            await vs.save_version(
                entity_type="skill",
                entity_id=slug,
                content=merged_content,
                change_source="auto",
            )
            await vs_session.commit()
        log.info("Updated existing skill", slug=slug)
        return f"updated: {slug}"

    elif match_result.startswith("NEW:"):
        # Step 4: 创建新 skill (draft)
        slug = match_result.removeprefix("NEW:").strip()

        # 确保 slug 合法
        import re

        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug) or len(slug) > 64:
            slug = "auto-" + incident_id[:8]

        try:
            service.create_skill(slug)
        except FileExistsError:
            slug = f"{slug}-{incident_id[:8]}"
            try:
                service.create_skill(slug)
            except FileExistsError:
                return f"skipped: could not create skill '{slug}'"

        # 确保 content 有 draft: true
        if "draft: true" not in content:
            content = content.replace("---\n", "---\ndraft: true\n", 1)

        log.info("Writing content to new skill", slug=slug, content_len=len(content))
        service.update_skill(slug, content)
        log.info("Created new draft skill", slug=slug)
        return f"created: {slug} (draft)"

    else:
        log.warning("Unexpected match result", result=match_result)
        return "skipped: unexpected match result"
