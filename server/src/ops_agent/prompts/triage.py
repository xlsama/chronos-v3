"""Triage 面谈提示词模板。"""

SUFFICIENCY_ASSESSMENT_PROMPT = """\
你是运维事件受理员。评估以下事件描述是否包含足够信息开始排查：

{description}

评估标准：
1. 是否描述了具体症状（错误信息/状态码/异常行为）
2. 是否有影响范围（哪些服务/用户/环境受影响）
3. 是否有时间线（何时开始/是否持续/是否有近期变更）

输出 JSON（不要 code block）：
{{"sufficient": true/false, "missing": ["缺失信息类型1", "缺失信息类型2"]}}"""

TRIAGE_QUESTION_PROMPT = """\
你是运维事件受理员。用户报告了以下事件，但缺少关键信息：

{description}

以下信息缺失：{missing}

请生成 1-2 个针对缺失信息的问题。输出纯文本问题，不要 JSON，不要工具调用。简明扼要。"""
