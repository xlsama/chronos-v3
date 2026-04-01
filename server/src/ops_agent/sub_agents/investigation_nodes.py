"""子 Agent 专用节点 —— 适配 InvestigationState 的 human_approval / ask_human / retry_tool_call。"""

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent._llm import build_multimodal_content, parse_resume
from src.ops_agent.state import InvestigationState
from src.ops_agent.tools.approval_validation import (
    build_missing_approval_explanation_retry_message,
    get_missing_approval_explanation_tool_name,
)
from src.ops_agent.tools.registry import APPROVAL_TOOL_NAMES

RETRY_MARKER = "[RETRY_TOOL_CALL]"
RETRY_MESSAGE = (
    f"{RETRY_MARKER}\n"
    "你刚才的回复没有调用任何工具。你必须始终以工具调用结束每一轮回复。\n"
    '- 需要向用户提问 → 调用 ask_human(question="你的具体问题")\n'
    "- 需要执行命令排查 → 调用对应的执行工具\n"
    "- 调查完成 → 调用 conclude(status=..., summary=..., detail=...)\n"
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
                    if tc["name"] in APPROVAL_TOOL_NAMES:
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
    approval_calls = [tc for tc in last_message.tool_calls if tc["name"] in APPROVAL_TOOL_NAMES]
    log.info("Initial entry", pending=len(approval_calls))
    return {
        "needs_approval": True,
        "pending_tool_call": approval_calls[0] if approval_calls else None,
    }


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

                text, images = parse_resume(user_response)
                messages = [ToolMessage(content=text, tool_call_id=tc["id"])]
                if images:
                    messages.append(
                        HumanMessage(
                            content=build_multimodal_content("用户补充了以下截图：", images)
                        )
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

    text, images = parse_resume(user_response)
    content = build_multimodal_content(text, images) if images else text

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
    last_message = state["messages"][-1] if state.get("messages") else None
    missing_tool_name = (
        await get_missing_approval_explanation_tool_name(last_message) if last_message else None
    )
    return {
        "messages": [
            HumanMessage(
                content=(
                    build_missing_approval_explanation_retry_message(missing_tool_name)
                    if missing_tool_name
                    else RETRY_MESSAGE
                )
            )
        ],
        "tool_call_retry_count": current_count + 1,
    }
