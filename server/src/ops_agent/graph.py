"""协调者图 —— coordinator_agent LLM 驱动的假设调度与排查管理。"""

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.nodes.coordinator_agent import (
    build_coordinator_tools,
    coordinator_agent_node,
    route_coordinator_decision,
)
from src.ops_agent.nodes.gather_context import gather_context_node
from src.ops_agent.nodes.planner import planner_node
from src.ops_agent.nodes.run_sub_agent import run_sub_agent_node
from src.ops_agent.state import CoordinatorState


# --- confirm_resolution ---


async def confirm_resolution_node(state: CoordinatorState) -> dict:
    sid = state["incident_id"][:8]
    log = get_logger(component="confirm_resolution", sid=sid)
    log.info("Waiting for user confirmation")
    user_response = interrupt({"type": "confirm_resolution"})
    log.info("User responded", response=str(user_response)[:100])

    if user_response == "confirmed":
        return {"is_complete": True}

    return {
        "messages": [HumanMessage(content=f"用户表示问题未解决: {user_response}")],
        "is_complete": False,
    }


def route_after_resolution(state: CoordinatorState) -> str:
    result = "end" if state.get("is_complete") else "coordinator_agent"
    get_logger(component="confirm_resolution", sid=state["incident_id"][:8]).info(
        "route_after_resolution", route=result
    )
    return result


# --- 审批/ask_human 透传节点 ---


async def sub_agent_approval_node(state: CoordinatorState) -> dict:
    """透传节点 — interrupt_before 已暂停图，resume 后直接通过，路由回 run_sub_agent。

    审批事件由 run_sub_agent 发布，审批决定通过 Command(update=...) 注入 state。
    此节点不调用 interrupt()，避免双重中断导致卡死。
    """
    log = get_logger(component="sub_agent_approval", sid=state["incident_id"][:8])
    log.info(
        "Sub-agent approval resumed",
        decision=state.get("approval_decision"),
    )
    return {}


async def sub_agent_ask_human_node(state: CoordinatorState) -> dict:
    """透传节点 — 仅用于触发 interrupt，让 AgentRunner 发布 ask_human 事件。"""
    log = get_logger(component="sub_agent_ask_human", sid=state["incident_id"][:8])
    log.info("Sub-agent ask_human interrupt")
    user_response = interrupt({"type": "sub_agent_ask_human"})
    log.info("Sub-agent ask_human resumed")

    # 从 resume 中提取文本和图片文件引用（不传 bytes，避免序列化风险）
    if isinstance(user_response, dict) and "text" in user_response:
        text = user_response["text"]
        images_meta = []
        for img in user_response.get("images") or []:
            images_meta.append({
                "filename": img.get("filename", ""),
                "stored_filename": img.get("stored_filename", ""),
                "content_type": img.get("content_type", "image/png"),
            })
        return {
            "messages": [HumanMessage(content=text)],
            "pending_human_images": images_meta if images_meta else None,
        }

    return {"messages": [HumanMessage(content=str(user_response))]}


# --- run_sub_agent 出口路由 ---


def route_after_sub_agent(state: CoordinatorState) -> str:
    """run_sub_agent 之后的路由：子 Agent 完成→coordinator，中断→透传节点。"""
    log = get_logger(component="route_after_sub_agent", sid=state["incident_id"][:8])
    sub_status = state.get("sub_agent_status")
    if sub_status == "waiting_for_human":
        if state.get("needs_approval"):
            log.info("-> sub_agent_approval")
            return "sub_agent_approval"
        log.info("-> sub_agent_ask_human")
        return "sub_agent_ask_human"
    log.info("-> coordinator_agent (sub-agent completed)")
    return "coordinator_agent"


# --- retry ---


async def coordinator_retry_node(state: CoordinatorState) -> dict:
    """coordinator_agent 未调用工具时重试。"""
    count = state.get("tool_call_retry_count", 0)
    get_logger(component="coordinator_retry", sid=state["incident_id"][:8]).info(
        "Retry", attempt=count + 1
    )
    return {
        "messages": [
            HumanMessage(
                content=(
                    "[RETRY_TOOL_CALL]\n"
                    "你刚才的回复没有调用任何工具。你必须始终以工具调用结束每轮回复。\n"
                    "- 启动子 Agent → 调用 launch_investigation(hypothesis_id, hypothesis_title, hypothesis_desc)\n"
                    "- 更新计划 → 调用 update_plan(plan_md)\n"
                    '- 排查完成 → 调用 complete(answer_md="结论")\n'
                    "请重新回复，这次必须调用一个工具。"
                )
            )
        ],
        "tool_call_retry_count": count + 1,
    }


# --- 图构建 ---


def build_graph():
    # coordinator 工具：仅 update_plan（launch_investigation 和 complete 由路由特殊处理）
    all_tools = build_coordinator_tools()
    # coordinator_tools ToolNode 只处理 update_plan
    regular_tools = [t for t in all_tools if t.name not in ("launch_investigation", "complete")]
    coordinator_tool_node = ToolNode(regular_tools)

    graph = StateGraph(CoordinatorState)

    graph.add_node("gather_context", gather_context_node)
    graph.add_node("planner", planner_node)
    graph.add_node("coordinator_agent", coordinator_agent_node)
    graph.add_node("coordinator_tools", coordinator_tool_node)
    graph.add_node("run_sub_agent", run_sub_agent_node)
    graph.add_node("confirm_resolution", confirm_resolution_node)
    graph.add_node("sub_agent_approval", sub_agent_approval_node)
    graph.add_node("sub_agent_ask_human", sub_agent_ask_human_node)
    graph.add_node("retry_tool_call", coordinator_retry_node)

    graph.set_entry_point("gather_context")

    graph.add_edge("gather_context", "planner")
    graph.add_edge("planner", "coordinator_agent")

    graph.add_conditional_edges(
        "coordinator_agent",
        route_coordinator_decision,
        {
            "launch_investigation": "run_sub_agent",
            "continue": "coordinator_tools",
            "complete": "confirm_resolution",
            "retry_tool_call": "retry_tool_call",
        },
    )

    graph.add_edge("coordinator_tools", "coordinator_agent")
    # run_sub_agent: 条件路由 — 子 Agent 完成→coordinator_agent，中断→透传节点
    graph.add_conditional_edges(
        "run_sub_agent",
        route_after_sub_agent,
        {
            "coordinator_agent": "coordinator_agent",
            "sub_agent_approval": "sub_agent_approval",
            "sub_agent_ask_human": "sub_agent_ask_human",
        },
    )
    graph.add_edge("sub_agent_approval", "run_sub_agent")
    graph.add_edge("sub_agent_ask_human", "run_sub_agent")
    graph.add_edge("retry_tool_call", "coordinator_agent")

    graph.add_conditional_edges(
        "confirm_resolution",
        route_after_resolution,
        {
            "end": END,
            "coordinator_agent": "coordinator_agent",
        },
    )

    return graph


def compile_graph(checkpointer=None):
    graph = build_graph()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["sub_agent_approval", "sub_agent_ask_human", "confirm_resolution"],
    )
