"""主图 —— main_agent LLM 驱动的假设调度与排查管理。"""

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from src.lib.logger import get_logger
from src.ops_agent.nodes.ask_human import ask_human_node
from src.ops_agent.nodes.main_agent import (
    build_main_tools,
    main_agent_node,
    route_main_decision,
)
from src.ops_agent.nodes.gather_context import gather_context_node
from src.ops_agent.nodes.planner import planner_node
from src.ops_agent.nodes.run_sub_agent import run_sub_agent_node
from src.ops_agent.state import MainState


# --- confirm_resolution ---


async def confirm_resolution_node(state: MainState) -> dict:
    sid = state["incident_id"][:8]
    log = get_logger(component="confirm_resolution", sid=sid)
    log.info("Waiting for user confirmation")
    user_response = interrupt({"type": "confirm_resolution"})
    log.info("User responded", response=str(user_response)[:100])

    if user_response == "confirmed":
        return {"is_complete": True}

    return {
        "messages": [
            HumanMessage(
                content=(
                    f"[用户反馈 - 问题未解决]\n"
                    f"用户消息: {user_response}\n\n"
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


# --- 审批/ask_human 透传节点 ---


async def sub_agent_approval_node(state: MainState) -> dict:
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


async def sub_agent_ask_human_node(state: MainState) -> dict:
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


# --- retry ---


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


# --- 图构建 ---


def build_graph():
    # main_agent 工具：update_plan / list_servers / list_services / read_skill 由 ToolNode 处理
    # launch_investigation、complete、ask_human 由路由特殊处理
    all_tools = build_main_tools()
    regular_tools = [
        t for t in all_tools if t.name not in ("launch_investigation", "complete", "ask_human")
    ]
    tool_node = ToolNode(regular_tools)

    graph = StateGraph(MainState)

    graph.add_node("gather_context", gather_context_node)
    graph.add_node("planner", planner_node)
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("run_sub_agent", run_sub_agent_node)
    graph.add_node("confirm_resolution", confirm_resolution_node)
    graph.add_node("sub_agent_approval", sub_agent_approval_node)
    graph.add_node("sub_agent_ask_human", sub_agent_ask_human_node)
    graph.add_node("ask_human", ask_human_node)
    graph.add_node("retry_tool_call", main_retry_node)

    graph.set_entry_point("gather_context")

    graph.add_edge("gather_context", "planner")
    graph.add_edge("planner", "main_agent")

    graph.add_conditional_edges(
        "main_agent",
        route_main_decision,
        {
            "launch_investigation": "run_sub_agent",
            "continue": "tools",
            "complete": "confirm_resolution",
            "ask_human": "ask_human",
            "retry_tool_call": "retry_tool_call",
        },
    )

    graph.add_edge("tools", "main_agent")
    graph.add_edge("ask_human", "main_agent")
    # run_sub_agent: 条件路由 — 子 Agent 完成→main_agent，中断→透传节点
    graph.add_conditional_edges(
        "run_sub_agent",
        route_after_sub_agent,
        {
            "main_agent": "main_agent",
            "sub_agent_approval": "sub_agent_approval",
            "sub_agent_ask_human": "sub_agent_ask_human",
        },
    )
    graph.add_edge("sub_agent_approval", "run_sub_agent")
    graph.add_edge("sub_agent_ask_human", "run_sub_agent")
    graph.add_edge("retry_tool_call", "main_agent")

    graph.add_conditional_edges(
        "confirm_resolution",
        route_after_resolution,
        {
            "end": END,
            "main_agent": "main_agent",
        },
    )

    return graph


def compile_graph(checkpointer=None):
    graph = build_graph()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["sub_agent_approval", "sub_agent_ask_human", "confirm_resolution"],
    )
