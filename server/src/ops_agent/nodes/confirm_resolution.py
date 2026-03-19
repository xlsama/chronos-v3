from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from src.ops_agent.state import OpsState


async def confirm_resolution_node(state: OpsState) -> dict:
    user_response = interrupt({"type": "confirm_resolution"})

    if user_response == "confirmed":
        return {"is_complete": True}

    # 用户选择继续排查 → 补全 complete tool call 的 ToolMessage + 用户新消息
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
    if state.get("is_complete"):
        return "end"
    return "main_agent"
