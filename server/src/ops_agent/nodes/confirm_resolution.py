from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.state import CoordinatorState


async def confirm_resolution_node(state: CoordinatorState) -> dict:
    sid = state["incident_id"][:8]
    log = get_logger(component="confirm_resolution", sid=sid)
    log.info("Entered confirm_resolution_node, waiting for user response")
    user_response = interrupt({"type": "confirm_resolution"})

    response_str = str(user_response)
    log.info("User responded", response_len=len(response_str))
    log.debug("User responded", response=response_str)

    if user_response == "confirmed":
        log.info("User confirmed resolution")
        return {"is_complete": True}

    log.info("User wants to continue investigation")
    return {
        "messages": [HumanMessage(content=f"用户表示问题未解决: {user_response}")],
        "is_complete": False,
    }


def route_after_resolution(state: CoordinatorState) -> str:
    sid = state["incident_id"][:8]
    log = get_logger(component="confirm_resolution", sid=sid)
    result = "end" if state.get("is_complete") else "main_agent"
    log.info("route_after_resolution", route=result)
    return result
