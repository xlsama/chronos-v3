from langchain_core.messages import HumanMessage

from src.lib.logger import get_logger
from src.ops_agent.state import OpsState

RETRY_MARKER = "[RETRY_TOOL_CALL]"

RETRY_MESSAGE = (
    f"{RETRY_MARKER}\n"
    "你刚才的回复没有调用任何工具。你必须始终以工具调用结束每一轮回复。\n"
    "- 需要向用户提问 → 调用 ask_human(question=\"你的具体问题\")\n"
    "- 需要执行命令排查 → 调用对应的执行工具\n"
    "- 排查已完成 → 调用 complete(answer_md=\"...\")\n"
    "请重新回复，这次必须调用一个工具。"
)


async def retry_tool_call_node(state: OpsState) -> dict:
    """LLM 未调用工具时，注入提示让其重试。"""
    sid = state["incident_id"][:8]
    current_count = state.get("tool_call_retry_count", 0)
    logger = get_logger(component="retry", sid=sid)
    logger.info("Retry tool call", attempt=current_count + 1)
    return {
        "messages": [HumanMessage(content=RETRY_MESSAGE)],
        "tool_call_retry_count": current_count + 1,
    }
