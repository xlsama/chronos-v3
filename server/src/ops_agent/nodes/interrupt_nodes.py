"""中断/路由/重试节点 —— 从 graph.py 提取的轻量节点函数。

包含:
- confirm_resolution / route_after_resolution
- agent_approval / agent_ask_human / route_after_agent
- parallel_agent_approval / parallel_agent_ask_human / route_after_parallel_agents
- verification_approval / verification_ask_human / route_after_verification
- main_retry_node
"""

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.state import MainState


# ═══════════════════════════════════════════
# confirm_resolution
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


async def agent_approval_node(state: MainState) -> dict:
    """透传节点 — interrupt_before 已暂停图，resume 后直接通过，路由回 run_agent。"""
    log = get_logger(component="agent_approval", sid=state["incident_id"][:8])
    log.info(
        "Agent approval resumed",
        decision=state.get("approval_decision"),
    )
    return {}


async def agent_ask_human_node(state: MainState) -> dict:
    """透传节点 — 仅用于触发 interrupt，让 AgentRunner 发布 ask_human 事件。"""
    log = get_logger(component="agent_ask_human", sid=state["incident_id"][:8])
    log.info("Agent ask_human interrupt")
    user_response = interrupt({"type": "agent_ask_human"})
    log.info("Agent ask_human resumed")

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


def route_after_agent(state: MainState) -> str:
    """run_agent 之后的路由：Agent 完成→main_agent，中断→透传节点。"""
    log = get_logger(component="route_after_agent", sid=state["incident_id"][:8])
    sub_status = state.get("agent_status")
    if sub_status == "waiting_for_human":
        if state.get("needs_approval"):
            log.info("-> agent_approval")
            return "agent_approval"
        log.info("-> agent_ask_human")
        return "agent_ask_human"
    log.info("-> main_agent (agent completed)")
    return "main_agent"


# ═══════════════════════════════════════════
# 并行 Agent 审批/ask_human 透传节点
# ═══════════════════════════════════════════


async def parallel_agent_approval_node(state: MainState) -> dict:
    """并行模式审批透传节点 — interrupt_before 暂停图，resume 后直接通过。"""
    log = get_logger(component="parallel_agent_approval", sid=state["incident_id"][:8])
    log.info(
        "Parallel agent approval resumed",
        decision=state.get("approval_decision"),
        agent_id=state.get("parallel_interrupted_agent_id"),
    )
    return {}


async def parallel_agent_ask_human_node(state: MainState) -> dict:
    """并行模式 ask_human 透传节点。"""
    log = get_logger(component="parallel_agent_ask_human", sid=state["incident_id"][:8])
    log.info("Parallel agent ask_human interrupt")
    user_response = interrupt({"type": "parallel_agent_ask_human"})
    log.info("Parallel agent ask_human resumed")

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


def route_after_parallel_agents(state: MainState) -> str:
    """run_parallel_agents 之后的路由。"""
    log = get_logger(
        component="route_after_parallel_agents", sid=state["incident_id"][:8]
    )
    interrupted_id = state.get("parallel_interrupted_agent_id")
    if not interrupted_id:
        log.info("-> main_agent (all parallel agents completed)")
        return "main_agent"

    parallel_agents = state.get("parallel_agents") or []
    agent = next((a for a in parallel_agents if a["hypothesis_id"] == interrupted_id), None)
    if not agent:
        log.warning("Interrupted agent not found, falling back to main_agent", id=interrupted_id)
        return "main_agent"

    if agent["status"] == "interrupted_human_approval":
        log.info("-> parallel_agent_approval", agent_id=interrupted_id)
        return "parallel_agent_approval"
    if agent["status"] == "interrupted_ask_human":
        log.info("-> parallel_agent_ask_human", agent_id=interrupted_id)
        return "parallel_agent_ask_human"

    log.info("-> main_agent (no active interrupt)")
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
                    "- 启动子 Agent → 调用 spawn_agent(hypothesis_id, hypothesis_title,"
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


# ═══════════════════════════════════════════
# Verification Sub-Agent 路由/透传节点
# ═══════════════════════════════════════════


def route_after_verification(state: MainState) -> str:
    """run_verification 之后的路由。"""
    log = get_logger(component="route_after_verification", sid=state["incident_id"][:8])
    status = state.get("verification_status")
    if status == "waiting_for_human":
        if state.get("needs_approval"):
            log.info("-> verification_approval")
            return "verification_approval"
        log.info("-> verification_ask_human")
        return "verification_ask_human"

    report = state.get("verification_report")
    if report and report.get("verdict") == "FAIL":
        log.info("-> main_agent (verification FAIL)")
        return "main_agent"

    log.info("-> confirm_resolution (verification PASS/PARTIAL)")
    return "confirm_resolution"


async def verification_approval_node(state: MainState) -> dict:
    """Verification 审批透传节点。"""
    log = get_logger(component="verification_approval", sid=state["incident_id"][:8])
    log.info("Verification approval resumed", decision=state.get("approval_decision"))
    return {}


async def verification_ask_human_node(state: MainState) -> dict:
    """Verification ask_human 透传节点。"""
    log = get_logger(component="verification_ask_human", sid=state["incident_id"][:8])
    log.info("Verification ask_human interrupt")
    user_response = interrupt({"type": "verification_ask_human"})
    log.info("Verification ask_human resumed")

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
