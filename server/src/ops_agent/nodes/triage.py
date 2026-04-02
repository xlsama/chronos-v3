"""Triage 面谈节点 —— 事件描述不充分时主动向用户收集关键信息。

在 gather_context 和 plan 之间运行。如果描述足够详细则直接跳过。
"""

import orjson
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.prompts.triage import SUFFICIENCY_ASSESSMENT_PROMPT, TRIAGE_QUESTION_PROMPT
from src.ops_agent.state import MainState


async def _assess_info_sufficiency(state: MainState) -> tuple[bool, list[str]]:
    """用 mini_model 评估事件描述信息是否充分。

    返回 (sufficient, missing_list)。
    """
    s = get_settings()
    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=False,
        extra_body={"enable_thinking": False},
    )

    prompt = SUFFICIENCY_ASSESSMENT_PROMPT.format(description=state.get("description", ""))
    response = await llm.ainvoke([SystemMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else ""

    try:
        result = orjson.loads(content)
        return result.get("sufficient", True), result.get("missing", [])
    except Exception:
        # JSON 解析失败时，用字符数兜底
        desc = state.get("description", "")
        return len(desc) >= 50, []


async def triage_node(state: MainState) -> dict:
    """如果事件描述不充分，通过 interrupt 向用户提问。否则直接跳过。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="triage", sid=sid)

    try:
        sufficient, missing = await _assess_info_sufficiency(state)
    except Exception as e:
        log.warning("Sufficiency assessment failed, skipping triage", error=str(e))
        return {}

    if sufficient:
        log.info("Description sufficient, skipping triage")
        return {}

    log.info("Description insufficient", missing=missing)

    s = get_settings()
    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=False,
        extra_body={"enable_thinking": False},
    )

    missing_text = ", ".join(missing) if missing else "具体症状、影响范围、时间线"
    messages = [
        SystemMessage(
            content=TRIAGE_QUESTION_PROMPT.format(
                description=state["description"],
                missing=missing_text,
            )
        ),
    ]

    try:
        response = await llm.ainvoke(messages)
        question = response.content if hasattr(response, "content") else ""
    except Exception as e:
        log.warning("Triage LLM failed, skipping triage", error=str(e))
        return {}

    if not question.strip():
        log.warning("Triage generated empty question, skipping")
        return {}

    log.info("Triage question generated", question_len=len(question))

    # Interrupt 等待用户回答
    user_response = interrupt({"type": "triage", "question": question})

    # 提取用户回答
    if isinstance(user_response, dict) and "text" in user_response:
        answer = user_response["text"]
    else:
        answer = str(user_response)

    # 将用户回答合并到 description
    enriched = f"{state['description']}\n\n## 补充信息\n{answer}"
    log.info("Description enriched", new_len=len(enriched))

    return {
        "description": enriched,
        "messages": [HumanMessage(content=f"[用户补充信息] {answer}")],
    }
