from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from src.lib.logger import logger
from src.ops_agent.state import OpsState


async def confirm_resolution_node(state: OpsState) -> dict:
    sid = state["incident_id"][:8]
    logger.info(f"[{sid}] [confirm_resolution] Entered confirm_resolution_node, waiting for user response")
    user_response = interrupt({"type": "confirm_resolution"})

    logger.info(f"[{sid}] [confirm_resolution] User responded: {str(user_response)[:200]}")

    # 注意：前端 event-timeline.tsx 中也硬编码发送此值，修改时需同步前端
    if user_response == "confirmed":
        logger.info(f"[{sid}] [confirm_resolution] User confirmed resolution")
        return {"is_complete": True}

    # 用户选择继续排查 → 补全 complete tool call 的 ToolMessage + 用户新消息
    logger.info(f"[{sid}] [confirm_resolution] User wants to continue investigation")
    new_messages = []
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "complete":
                    new_messages.append(ToolMessage(
                        content="用户表示问题未解决，需要继续排查。",
                        tool_call_id=tc["id"],
                    ))
            break
    new_messages.append(HumanMessage(content=user_response))
    return {"messages": new_messages, "is_complete": False}


def route_after_resolution(state: OpsState) -> str:
    sid = state["incident_id"][:8]
    result = "end" if state.get("is_complete") else "main_agent"
    logger.info(f"[{sid}] [confirm_resolution] route_after_resolution -> {result}")
    return result
