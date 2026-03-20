from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.state import OpsState


async def ask_human_node(state: OpsState) -> dict:
    """Interrupt the graph to ask the human a question.

    Uses LangGraph's interrupt() to pause execution.
    Handles two cases:
    1. Agent used ask_human tool → extract question from tool_call, return ToolMessage
    2. Agent replied with plain text (no tool_calls, retry exhausted) → use LLM text as question
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="ask_human", sid=sid)
    last_msg = state["messages"][-1]
    current_count = state.get("ask_human_count", 0)

    # Case 1: explicit ask_human tool call
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == "ask_human":
                question = tc["args"].get("question", "")
                log.info("Interrupt (explicit)", question=question[:100])
                user_response = interrupt({"question": question})
                log.info("Resume", response_len=len(str(user_response)))
                return {
                    "messages": [ToolMessage(content=str(user_response), tool_call_id=tc["id"])],
                    "ask_human_count": current_count + 1,
                    "tool_call_retry_count": 0,
                }

    # Case 2: plain text response (no tool calls) — fallback after retry exhausted
    question = last_msg.content if hasattr(last_msg, "content") and last_msg.content else "请补充更多信息以便继续排查。"
    log.info("Interrupt (fallback)", question=question[:100])
    user_response = interrupt({"question": question})
    log.info("Resume", response_len=len(str(user_response)))
    return {
        "messages": [HumanMessage(content=str(user_response))],
        "ask_human_count": current_count + 1,
        "tool_call_retry_count": 0,
    }
