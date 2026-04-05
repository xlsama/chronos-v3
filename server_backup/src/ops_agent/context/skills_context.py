"""Skill 上下文构建。

借鉴 Claude Code 的 skill listing 设计：
- description + when_to_use 合并展示，帮助 Agent 准确匹配技能
- Token 预算控制（MAX_LISTING_CHARS），超出时自动截断描述
- 两层格式：full（≤10 个）/ compact（>10 个）
"""

from src.lib.logger import get_logger
from src.services.skill_service import SkillService

_COMPACT_THRESHOLD = 10

# 参考 Claude Code: skill listing 占上下文的预算上限（字符数）
# Claude Code 用 1% context window，这里按 8000 字符（约 2000 token）
MAX_LISTING_CHARS = 8000

# 单条 skill 描述的最大字符数（含 when_to_use），防止单条过长
MAX_DESC_CHARS = 250

_USAGE_RULES = """\
使用规则:
1. 通用技能优先: 若存在 `incident-triage`，先 skill_read 获取分诊骨架，再切到专项技能。
2. 渐进加载: 先读 SKILL.md 主体获取流程概要；scripts/references 等子文件只在执行到相关步骤时按需加载。
3. 上下文控制: 技能内容较长时，总结关键步骤和命令，不要大段复制粘贴原文。
4. 多技能协调: 多个技能同时匹配时，选最小必要集合，声明使用顺序和原因。
5. 缺失回退: 若匹配的技能无法读取或不适用当前场景，用通用排查方法继续。"""


def _build_skill_desc(skill: dict) -> str:
    """合并 description + when_to_use，截断到 MAX_DESC_CHARS。

    参考 Claude Code 的 getCommandDescription:
      desc = cmd.whenToUse ? `${cmd.description} - ${cmd.whenToUse}` : cmd.description
    """
    desc = skill["description"]
    when = skill.get("when_to_use", "")
    if when:
        desc = f"{desc} - {when}"
    if len(desc) > MAX_DESC_CHARS:
        desc = desc[: MAX_DESC_CHARS - 1] + "…"
    return desc


def build_skills_context(
    skill_service: SkillService,
    *,
    related_services: list[str] | None = None,
) -> str:
    """构建 skills 上下文，注入 Agent 系统提示词。

    Args:
        skill_service: SkillService 实例
        related_services: 当前事件关联的服务类型列表（可选），
                         有值时优先展示匹配的技能
    """
    skill_log = get_logger(component="skill")
    available = skill_service.get_available_skills()

    if not available:
        skill_log.info("No available skills")
        return ""

    # 按关联服务排序：匹配的排前面
    if related_services:
        svc_set = {s.lower() for s in related_services}

        def _match_score(s: dict) -> int:
            skill_svcs = {v.lower() for v in s.get("related_services", [])}
            skill_tags = {v.lower() for v in s.get("tags", [])}
            return -len((skill_svcs | skill_tags) & svc_set)

        available = sorted(available, key=_match_score)

    slugs = [s["slug"] for s in available]
    fmt = "compact" if len(available) > _COMPACT_THRESHOLD else "full"
    skill_log.info(
        "build_skills_context",
        count=len(available),
        format=fmt,
        slugs=slugs,
    )

    xml_lines = ["\n<available_skills>", _USAGE_RULES]

    # Token 预算：跟踪已用字符数
    used_chars = sum(len(line) for line in xml_lines)

    for s in available:
        desc = _build_skill_desc(s)
        tags_str = ", ".join(s.get("tags", []))

        if fmt == "compact":
            if tags_str:
                entry = f'  <skill name="{s["slug"]}" tags="{tags_str}">{desc}</skill>'
            else:
                entry = f'  <skill name="{s["slug"]}">{desc}</skill>'
        else:
            parts = [f'  <skill>\n    <name>{s["slug"]}</name>']
            parts.append(f"    <description>{desc}</description>")
            if tags_str:
                parts.append(f"    <tags>{tags_str}</tags>")
            parts.append("  </skill>")
            entry = "\n".join(parts)

        # 预算检查
        if used_chars + len(entry) > MAX_LISTING_CHARS:
            shown = sum(1 for line in xml_lines if "<skill" in line)
            remaining = len(available) - shown
            if remaining > 0:
                xml_lines.append(
                    f"  <!-- {remaining} more skills available, "
                    f'use skill_read("?") to see full list -->'
                )
            skill_log.info(
                "skill listing truncated by budget",
                shown=len(available) - remaining,
                total=len(available),
            )
            break

        xml_lines.append(entry)
        used_chars += len(entry)

    xml_lines.append("</available_skills>")
    return "\n".join(xml_lines)
