"""排查结论生成节点 —— 汇总所有假设调查结果，生成最终结论。"""

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.prompts.synthesize import SYNTHESIZE_SYSTEM_PROMPT, SYNTHESIZE_USER_PROMPT
from src.ops_agent.state import CoordinatorState


def _format_investigation_results(state: CoordinatorState) -> str:
    """将所有假设调查结果格式化为可读文本。"""
    results = state.get("hypothesis_results") or []
    if not results:
        return "（无调查结果）"

    lines = []
    for r in results:
        status_map = {
            "confirmed": "已确认",
            "eliminated": "已排除",
            "inconclusive": "证据不足",
        }
        status_zh = status_map.get(r["status"], r["status"])
        lines.append(f"### {r['hypothesis_id']} [{status_zh}] {r['hypothesis_desc']}")
        lines.append(f"**调查摘要**: {r['summary']}")
        if r.get("evidence"):
            lines.append(f"**关键证据**: {r['evidence']}")
        lines.append("")
    return "\n".join(lines)


async def synthesize_node(state: CoordinatorState) -> dict:
    """汇总所有假设调查结果，生成最终排查结论。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="synthesize", sid=sid)
    log.info("===== Synthesize started =====")

    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
    )

    investigation_results = _format_investigation_results(state)
    user_prompt = SYNTHESIZE_USER_PROMPT.format(
        description=state["description"],
        investigation_results=investigation_results,
    )

    t0 = time.monotonic()
    response = await llm.ainvoke([
        SystemMessage(content=SYNTHESIZE_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    elapsed = time.monotonic() - t0

    answer_md = response.content.strip()
    log.info("===== Synthesize completed =====", elapsed=f"{elapsed:.2f}s", chars=len(answer_md))

    # 将排查结论存入消息（供 confirm_resolution 后续使用）
    return {
        "messages": [HumanMessage(content=f"[排查结论]\n\n{answer_md}")],
    }
