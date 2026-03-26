from langchain_core.messages import HumanMessage

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.state import OpsState

RETRY_MARKER = "[RETRY_TOOL_CALL]"

RETRY_MESSAGE = (
    f"{RETRY_MARKER}\n"
    "你刚才的回复没有调用任何工具。你必须始终以工具调用结束每一轮回复。\n"
    '- 需要向用户提问 → 调用 ask_human(question="你的具体问题")\n'
    "- 需要执行命令排查 → 调用对应的执行工具\n"
    "- 获得新证据 → 调用 update_plan 更新假设状态（标记 [confirmed] 会自动触发验证）\n"
    "请重新回复，这次必须调用一个工具。"
)


async def retry_tool_call_node(state: OpsState) -> dict:
    """LLM 未调用工具时，注入提示让其重试。"""
    sid = state["incident_id"][:8]
    current_count = state.get("tool_call_retry_count", 0)
    max_retries = get_settings().tool_call_max_retries
    logger = get_logger(component="retry", sid=sid)

    last_msg = state["messages"][-1]
    content_preview = ""
    if hasattr(last_msg, "content") and last_msg.content:
        content_preview = last_msg.content[:200]

    logger.info(
        "Retry tool call",
        attempt=current_count + 1,
        max_retries=max_retries,
        last_msg_content_preview=content_preview,
    )
    return {
        "messages": [HumanMessage(content=RETRY_MESSAGE)],
        "tool_call_retry_count": current_count + 1,
    }
