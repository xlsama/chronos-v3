"""可组合的提示词公共片段与动态 prompt 组装。

所有 Agent 系统提示词的公共部分抽取为函数，消除重复并统一处理。
"""

# ---------------------------------------------------------------------------
# 防护前缀：用于 compact 等不需要工具调用的场景
# ---------------------------------------------------------------------------

NO_TOOLS_PREAMBLE = """\
重要：只输出纯文本。不要调用任何工具。
你已有所有需要的上下文，工具调用会被拒绝。
输出��式：先 <analysis> 块，再 <summary> 块。"""

# ---------------------------------------------------------------------------
# 输出效率 Section
# ---------------------------------------------------------------------------

OUTPUT_EFFICIENCY_SECTION = """\
## 输出效率

直奔重点。先用最简单的方法，不要绕圈子。

重点输出：
- 需要用户决策的信息
- 关键阶段的状态更新
- 改变排查方向的错误或阻塞

一句话能说清的不要用三句。用陈述句，不用疑问句。分析用中文，技术术语保持原文。
必须以工具调用结束每轮回复。"""


def get_context_sections(
    *,
    incident_history: str | None = None,
    kb_summary: str | None = None,
    plan: str | None = None,
    skills: str | None = None,
    compact_md: str | None = None,
    prior_findings: str | None = None,
) -> str:
    """动态拼接非空上下文 section，跳过空值。"""
    label_map = {
        "incident_history": (
            "历史事件参考",
            "以下是与当前事件描述相似的历史事件（仅供参考，不代表当前根因相同）：\n\n",
        ),
        "kb_summary": ("项目知识库上下文", ""),
        "plan": ("当前调查计划", ""),
        "skills": (None, ""),  # skills 自带标题
        "compact_md": ("排查进展摘要（上下文压缩后）", ""),
        "prior_findings": ("之前的调查发现", ""),
    }

    values = {
        "incident_history": incident_history,
        "kb_summary": kb_summary,
        "plan": plan,
        "skills": skills,
        "compact_md": compact_md,
        "prior_findings": prior_findings,
    }

    sections: list[str] = []
    for key, (label, prefix) in label_map.items():
        value = values.get(key)
        if not value:
            continue
        if label is None:
            # skills 自带完整格式
            sections.append(value)
        else:
            sections.append(f"## {label}\n\n{prefix}{value}")

    return "\n\n".join(sections)


def build_system_prompt(
    template: str,
    *,
    description: str,
    severity: str = "",
    incident_history: str | None = None,
    kb_summary: str | None = None,
    plan: str | None = None,
    skills: str = "",
    compact_md: str | None = None,
    prior_findings: str | None = None,
    **extra_vars: str,
) -> str:
    """组装完整系统 prompt = template.format(context_sections=..., **vars)。

    统一当前各 agent 节点中重复的 prompt 拼装模式���
    """
    context_sections = get_context_sections(
        incident_history=incident_history,
        kb_summary=kb_summary,
        plan=plan,
        skills=skills,
        compact_md=compact_md,
        prior_findings=prior_findings,
    )
    return template.format(
        description=description,
        severity=severity,
        context_sections=context_sections,
        **extra_vars,
    )
