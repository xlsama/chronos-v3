from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from src.ops_agent.state import OpsState


async def ask_human_node(state: OpsState) -> dict:
    """Interrupt the graph to ask the human a question.

    Uses LangGraph's interrupt() to pause execution.
    Handles two cases:
    1. Agent used ask_human tool → extract question from tool_call, return ToolMessage
    2. Agent replied with plain text (no tool_calls) → use text as question, return HumanMessage
    """
    last_msg = state["messages"][-1]

    # Case 1: explicit ask_human tool call
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == "ask_human":
                question = tc["args"].get("question", "")
                user_response = interrupt({"question": question})
                return {
                    "messages": [ToolMessage(content=str(user_response), tool_call_id=tc["id"])]
                }

    # Case 2: plain text response (no tool calls) — agent is sharing analysis or asking implicitly
    question = last_msg.content if hasattr(last_msg, "content") else ""
    user_response = interrupt({"question": question})
    return {
        "messages": [HumanMessage(content=str(user_response))]
    }
