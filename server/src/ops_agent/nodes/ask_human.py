import base64

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.state import OpsState


def _parse_resume(user_response) -> tuple[str, list[dict]]:
    """Extract text and optional images from a resume value.

    Resume can be:
    - str: plain text
    - dict: {"text": "...", "images": [{"filename", "bytes", "content_type"}]}
    """
    if isinstance(user_response, dict) and "text" in user_response:
        text = user_response["text"]
        images = user_response.get("images") or []
        return text, images
    return str(user_response), []


def _build_multimodal_content(text: str, images: list[dict]) -> list[dict]:
    """Build LangChain multimodal content blocks."""
    blocks: list[dict] = [{"type": "text", "text": text}]
    for img in images[:5]:
        b64 = base64.b64encode(img["bytes"]).decode()
        mime = img.get("content_type") or "image/png"
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )
    return blocks


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
                log.info(
                    "Interrupt (explicit ask_human tool call)",
                    question=question[:200],
                    ask_human_count=current_count + 1,
                    tool_call_retry_count=state.get("tool_call_retry_count", 0),
                )
                user_response = interrupt({"question": question})
                log.info("Resume", response_len=len(str(user_response)))
                log.info(
                    "Resetting tool_call_retry_count",
                    from_count=state.get("tool_call_retry_count", 0),
                )

                text, images = _parse_resume(user_response)
                messages = [ToolMessage(content=text, tool_call_id=tc["id"])]
                # Append a multimodal HumanMessage if images are present
                if images:
                    messages.append(
                        HumanMessage(
                            content=_build_multimodal_content("用户补充了以下截图：", images),
                        )
                    )

                return {
                    "messages": messages,
                    "ask_human_count": current_count + 1,
                    "tool_call_retry_count": 0,
                }

    # Case 2: plain text response (no tool calls) — fallback after retry exhausted
    question = (
        last_msg.content
        if hasattr(last_msg, "content") and last_msg.content
        else "请补充更多信息以便继续排查。"
    )
    retry_count = state.get("tool_call_retry_count", 0)
    log.info(
        "Interrupt (fallback after retry exhaustion)",
        question=question[:200],
        ask_human_count=current_count + 1,
        tool_call_retry_count=retry_count,
    )
    user_response = interrupt({"question": question})
    log.info("Resume", response_len=len(str(user_response)))
    log.info("Resetting tool_call_retry_count", from_count=state.get("tool_call_retry_count", 0))

    text, images = _parse_resume(user_response)
    if images:
        content = _build_multimodal_content(text, images)
    else:
        content = text

    return {
        "messages": [HumanMessage(content=content)],
        "ask_human_count": current_count + 1,
        "tool_call_retry_count": 0,
    }
