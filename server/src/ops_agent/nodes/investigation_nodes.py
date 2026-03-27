"""子 Agent 专用节点 —— 适配 InvestigationState 的 human_approval / ask_human / retry_tool_call。"""

import base64

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.state import InvestigationState

_APPROVAL_TOOLS = {"ssh_bash", "bash", "service_exec"}

RETRY_MARKER = "[RETRY_TOOL_CALL]"
RETRY_MESSAGE = (
    f"{RETRY_MARKER}\n"
    "你刚才的回复没有调用任何工具。你必须始终以工具调用结束每一轮回复。\n"
    '- 需要向用户提问 → 调用 ask_human(question="你的具体问题")\n'
    "- 需要执行命令排查 → 调用对应的执行工具\n"
    '- 调查完成 → 调用 report_findings(status=..., summary=..., report=...)\n'
    "请重新回复，这次必须调用一个工具。"
)


async def investigation_human_approval_node(state: InvestigationState) -> dict:
    """子 Agent 的审批节点。逻辑与主 Agent 的 human_approval_node 相同。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="inv_approval", sid=sid)
    decision = state.get("approval_decision")

    if decision:
        log.info("Resume", decision=decision)
        if decision in ("rejected", "supplemented"):
            supplement = state.get("approval_supplement")
            content = (
                f"用户拒绝了该命令并补充说明: {supplement}\n请根据用户的补充信息重新思考方案。"
                if decision == "supplemented" and supplement
                else "用户拒绝了该命令，请换一个方案继续排查。"
            )
            last_message = state["messages"][-1]
            tool_messages = []
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                for tc in last_message.tool_calls:
                    if tc["name"] in _APPROVAL_TOOLS:
                        tool_messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))
            return {
                "messages": tool_messages,
                "needs_approval": False,
                "pending_tool_call": None,
                "approval_supplement": None,
            }

        # Approved
        log.info("Approved")
        return {
            "needs_approval": False,
            "pending_tool_call": None,
            "approval_decision": None,
            "approval_supplement": None,
        }

    # Initial entry
    last_message = state["messages"][-1]
    approval_calls = [tc for tc in last_message.tool_calls if tc["name"] in _APPROVAL_TOOLS]
    log.info("Initial entry", pending=len(approval_calls))
    return {
        "needs_approval": True,
        "pending_tool_call": approval_calls[0] if approval_calls else None,
    }


def _parse_resume(user_response) -> tuple[str, list[dict]]:
    if isinstance(user_response, dict) and "text" in user_response:
        return user_response["text"], user_response.get("images") or []
    return str(user_response), []


def _build_multimodal_content(text: str, images: list[dict]) -> list[dict]:
    blocks: list[dict] = [{"type": "text", "text": text}]
    for img in images[:5]:
        b64 = base64.b64encode(img["bytes"]).decode()
        mime = img.get("content_type") or "image/png"
        blocks.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return blocks


async def investigation_ask_human_node(state: InvestigationState) -> dict:
    """子 Agent 的 ask_human 节点。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="inv_ask_human", sid=sid)
    last_msg = state["messages"][-1]
    current_count = state.get("ask_human_count", 0)

    # Case 1: explicit ask_human tool call
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == "ask_human":
                question = tc["args"].get("question", "")
                log.info("Interrupt (ask_human)", question=question[:200])
                user_response = interrupt({"question": question})
                log.info("Resume", response_len=len(str(user_response)))

                text, images = _parse_resume(user_response)
                messages = [ToolMessage(content=text, tool_call_id=tc["id"])]
                if images:
                    messages.append(
                        HumanMessage(content=_build_multimodal_content("用户补充了以下截图：", images))
                    )
                return {
                    "messages": messages,
                    "ask_human_count": current_count + 1,
                    "tool_call_retry_count": 0,
                }

    # Case 2: plain text response (fallback)
    question = (
        last_msg.content
        if hasattr(last_msg, "content") and last_msg.content
        else "请补充更多信息以便继续排查。"
    )
    log.info("Interrupt (fallback)", question=question[:200])
    user_response = interrupt({"question": question})

    text, images = _parse_resume(user_response)
    content = _build_multimodal_content(text, images) if images else text

    return {
        "messages": [HumanMessage(content=content)],
        "ask_human_count": current_count + 1,
        "tool_call_retry_count": 0,
    }


async def investigation_retry_tool_call_node(state: InvestigationState) -> dict:
    """子 Agent 的 retry_tool_call 节点。"""
    sid = state["incident_id"][:8]
    current_count = state.get("tool_call_retry_count", 0)
    log = get_logger(component="inv_retry", sid=sid)
    log.info("Retry tool call", attempt=current_count + 1)
    return {
        "messages": [HumanMessage(content=RETRY_MESSAGE)],
        "tool_call_retry_count": current_count + 1,
    }
