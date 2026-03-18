from langgraph.types import interrupt

from src.lib.logger import logger
from src.ops_agent.state import OpsState


async def confirm_context_node(state: OpsState) -> dict:
    """Interrupt to let the user confirm or supplement KB context before main agent starts."""
    sid = state["incident_id"][:8]
    kb_summary = state.get("kb_summary", "")

    # If KB context is incomplete, ask user to supplement
    if not kb_summary or "[需要补充]" in kb_summary:
        logger.info(f"[{sid}] [confirm_context] KB context incomplete, requesting user input")
        response = interrupt({
            "type": "kb_context_incomplete",
            "summary": kb_summary.replace("\n\n[需要补充]", "") if kb_summary else "",
            "message": "知识库检索信息不足，请补充相关上下文",
        })
        # User provided supplementary info
        if isinstance(response, str) and response.strip():
            updated = kb_summary.replace("\n\n[需要补充]", "") if kb_summary else ""
            updated += f"\n\n## 用户补充信息\n{response}"
            return {"kb_summary": updated, "kb_context_confirmed": True}
        return {"kb_context_confirmed": True}

    # KB context is sufficient, ask user to confirm
    logger.info(f"[{sid}] [confirm_context] KB context sufficient, requesting confirmation")
    response = interrupt({
        "type": "kb_context_confirm",
        "summary": kb_summary,
        "message": "请确认以下知识库检索结果是否正确",
    })

    if response == "confirmed":
        return {"kb_context_confirmed": True}

    # User provided correction
    if isinstance(response, str) and response.strip():
        corrected = kb_summary + f"\n\n## 用户补充信息\n{response}"
        return {"kb_summary": corrected, "kb_context_confirmed": True}

    return {"kb_context_confirmed": True}
