"""中断/路由/重试节点 —— 从 graph.py 提取的轻量节点函数。

包含:
- 意图路由: route_after_classify
- QA 通道: qa_retry_node, qa_approval_node
- Incident 通道: confirm_resolution_node, route_after_resolution,
  sub_agent_approval_node, sub_agent_ask_human_node, route_after_sub_agent,
  main_retry_node
"""

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.state import MainState
from src.ops_agent.tools.approval_validation import (
    build_missing_approval_explanation_retry_message,
    get_missing_approval_explanation_tool_name,
)


# ═══════════════════════════════════════════
# 意图路由
# ═══════════════════════════════════════════


def route_after_classify(state: MainState) -> str:
    """意图分类后路由：incident 走完整排查管线，question/task 走轻量路径。"""
    intent = state.get("intent", "incident")
    log = get_logger(component="route", sid=state["incident_id"][:8])
    if intent in ("question", "task"):
        log.info("-> gather_context (QA path)", intent=intent)
        return "gather_context_qa"
    log.info("-> gather_context (incident path)")
    return "gather_context"


# ═══════════════════════════════════════════
# QA 通道节点
# ═══════════════════════════════════════════


async def qa_retry_node(state: MainState) -> dict:
    """QA Agent 未调用工具时重试。"""
    count = state.get("tool_call_retry_count", 0)
    get_logger(component="qa_retry", sid=state["incident_id"][:8]).info("Retry", attempt=count + 1)
    last_message = state["messages"][-1] if state.get("messages") else None
    missing_tool_name = (
        await get_missing_approval_explanation_tool_name(last_message) if last_message else None
    )
    retry_content = (
        build_missing_approval_explanation_retry_message(missing_tool_name)
        if missing_tool_name
        else (
            "[RETRY_TOOL_CALL]\n"
            "你刚才的回复没有调用任何工具。你必须以工具调用结束每轮回复。\n"
            '- 回答完毕 → 调用 complete(answer_md="回答内容")\n'
            "- 需要查看信息 → 调用 list_servers / list_services / ssh_bash / bash 等\n"
            "- 缺少信息 → 调用 ask_human(question)\n"
            "请重新回复，这次必须调用一个工具。"
        )
    )
    return {
        "messages": [HumanMessage(content=retry_content)],
        "tool_call_retry_count": count + 1,
    }


async def qa_approval_node(state: MainState) -> dict:
    """QA 通道的审批节点 — 用于 task 类型中涉及写操作的场景。"""
    log = get_logger(component="qa_approval", sid=state["incident_id"][:8])
    log.info("QA approval interrupt")
    user_response = interrupt({"type": "qa_approval"})
    log.info("QA approval resumed", response=str(user_response)[:100])

    if isinstance(user_response, dict):
        decision = user_response.get("decision", "approved")
    else:
        decision = str(user_response)

    if decision == "rejected":
        return {
            "messages": [
                HumanMessage(content="[用户拒绝了该操作] 请调整方案或用 complete 告知用户。")
            ],
            "approval_decision": "rejected",
        }

    return {"approval_decision": "approved"}


# ═══════════════════════════════════════════
# confirm_resolution（incident 路径）
# ═══════════════════════════════════════════


async def confirm_resolution_node(state: MainState) -> dict:
    sid = state["incident_id"][:8]
    log = get_logger(component="confirm_resolution", sid=sid)
    log.info("Waiting for user confirmation")
    user_response = interrupt({"type": "confirm_resolution"})
    log.info("User responded", response=str(user_response)[:100])

    if user_response == "confirmed":
        return {"is_complete": True}

    if isinstance(user_response, dict) and "text" in user_response:
        text = user_response["text"]
    else:
        text = str(user_response)

    return {
        "messages": [
            HumanMessage(
                content=(
                    f"[用户反馈 - 问题未解决]\n"
                    f"用户消息: {text}\n\n"
                    f"用户明确表示上一轮排查结论未能解决问题。"
                    f"请根据用户反馈重新分析，继续排查。"
                )
            )
        ],
        "is_complete": False,
    }


def route_after_resolution(state: MainState) -> str:
    result = "end" if state.get("is_complete") else "main_agent"
    get_logger(component="confirm_resolution", sid=state["incident_id"][:8]).info(
        "route_after_resolution", route=result
    )
    return result


# ═══════════════════════════════════════════
# 审批/ask_human 透传节点（incident 路径）
# ═══════════════════════════════════════════


async def sub_agent_approval_node(state: MainState) -> dict:
    """透传节点 — interrupt_before 已暂停图，resume 后直接通过，路由回 run_sub_agent。"""
    log = get_logger(component="sub_agent_approval", sid=state["incident_id"][:8])
    log.info(
        "Sub-agent approval resumed",
        decision=state.get("approval_decision"),
    )
    return {}


async def sub_agent_ask_human_node(state: MainState) -> dict:
    """透传节点 — 仅用于触发 interrupt，让 AgentRunner 发布 ask_human 事件。"""
    log = get_logger(component="sub_agent_ask_human", sid=state["incident_id"][:8])
    log.info("Sub-agent ask_human interrupt")
    user_response = interrupt({"type": "sub_agent_ask_human"})
    log.info("Sub-agent ask_human resumed")

    if isinstance(user_response, dict) and "text" in user_response:
        text = user_response["text"]
        images_meta = []
        for img in user_response.get("images") or []:
            images_meta.append(
                {
                    "filename": img.get("filename", ""),
                    "stored_filename": img.get("stored_filename", ""),
                    "content_type": img.get("content_type", "image/png"),
                }
            )
        return {
            "messages": [HumanMessage(content=text)],
            "pending_human_images": images_meta if images_meta else None,
        }

    return {"messages": [HumanMessage(content=str(user_response))]}


def route_after_sub_agent(state: MainState) -> str:
    """run_sub_agent 之后的路由：子 Agent 完成→main_agent，中断→透传节点。"""
    log = get_logger(component="route_after_sub_agent", sid=state["incident_id"][:8])
    sub_status = state.get("sub_agent_status")
    if sub_status == "waiting_for_human":
        if state.get("needs_approval"):
            log.info("-> sub_agent_approval")
            return "sub_agent_approval"
        log.info("-> sub_agent_ask_human")
        return "sub_agent_ask_human"
    log.info("-> main_agent (sub-agent completed)")
    return "main_agent"


# ═══════════════════════════════════════════
# retry（incident 路径）
# ═══════════════════════════════════════════


async def main_retry_node(state: MainState) -> dict:
    """main_agent 未调用工具时重试。"""
    count = state.get("tool_call_retry_count", 0)
    get_logger(component="main_retry", sid=state["incident_id"][:8]).info(
        "Retry", attempt=count + 1
    )
    return {
        "messages": [
            HumanMessage(
                content=(
                    "[RETRY_TOOL_CALL]\n"
                    "你刚才的回复没有调用任何工具。你必须始终以工具调用结束每轮回复。\n"
                    "- 启动子 Agent → 调用 launch_investigation(hypothesis_id, hypothesis_title,"
                    " hypothesis_desc)\n"
                    "- 更新计划 → 调用 update_plan(plan_md)\n"
                    "- 向用户提问 → 调用 ask_human(question)\n"
                    '- 排查完成 → 调用 complete(answer_md="结论")\n'
                    "请重新回复，这次必须调用一个工具。"
                )
            )
        ],
        "tool_call_retry_count": count + 1,
    }
