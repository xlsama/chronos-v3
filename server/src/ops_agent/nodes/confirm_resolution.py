from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.state import OpsState


async def confirm_resolution_node(state: OpsState) -> dict:
    sid = state["incident_id"][:8]
    log = get_logger(component="confirm_resolution", sid=sid)
    log.info("Entered confirm_resolution_node, waiting for user response")
    user_response = interrupt({"type": "confirm_resolution"})

    log.info("User responded", response=str(user_response)[:200])

    if user_response == "confirmed":
        log.info("User confirmed resolution")
        return {"is_complete": True}

    log.info("User wants to continue investigation")
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
    log = get_logger(component="confirm_resolution", sid=sid)
    result = "end" if state.get("is_complete") else "main_agent"
    log.info("route_after_resolution", route=result)
    return result
