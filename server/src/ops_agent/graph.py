from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.lib.logger import get_logger
from src.ops_agent.nodes.ask_human import ask_human_node
from src.ops_agent.nodes.compact_context import compact_context_node, should_compact
from src.ops_agent.nodes.confirm_resolution import confirm_resolution_node, route_after_resolution
from src.ops_agent.nodes.gather_context import gather_context_node
from src.ops_agent.nodes.human_approval import human_approval_node
from src.ops_agent.nodes.main_agent import build_tools, main_agent_node, route_decision
from src.ops_agent.nodes.planner import planner_node
from src.ops_agent.nodes.retry_tool_call import retry_tool_call_node
from src.ops_agent.state import OpsState


def route_after_approval(state: OpsState) -> str:
    """Route after human_approval: rejected/supplemented goes back to LLM, approved goes to tools."""
    sid = state["incident_id"][:8]
    log = get_logger(component="approval", sid=sid)
    decision = state.get("approval_decision", "approved")
    route = "main_agent" if decision in ("rejected", "supplemented") else "tools"
    log.info("route_after_approval", decision=decision, route=route)
    return route


def _has_hypothesis_transition(state: OpsState) -> bool:
    """检测最近一轮 tool 执行中 update_plan 是否触发了假设状态变更。

    update_plan 工具在检测到假设从 pending/investigating 变为 confirmed/eliminated 时，
    会在返回值中包含"假设状态已变更"。检查 ToolMessage 的 content 来判断。
    """
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_call_id") and "假设状态已变更" in (msg.content or ""):
            return True
        # 遇到 AIMessage（有 tool_calls）就停止，只检查最近一轮的 ToolMessage
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            break
    return False


def route_after_tools(state: OpsState) -> str:
    """Route after tools: check hypothesis transition, then context compaction."""
    sid = state["incident_id"][:8]
    log = get_logger(component="router", sid=sid)

    # 假设状态变更（confirmed/eliminated）→ 压缩上下文，开启新轮次
    if _has_hypothesis_transition(state):
        log.info("route_after_tools -> compact_context (hypothesis transition)")
        return "compact_context"

    if should_compact(state):
        log.info("route_after_tools -> compact_context", message_count=len(state["messages"]))
        return "compact_context"

    return "main_agent"


def build_graph():
    all_tools = build_tools()
    tool_node = ToolNode(all_tools)

    graph = StateGraph(OpsState)

    # Add nodes
    graph.add_node("gather_context", gather_context_node)
    graph.add_node("planner", planner_node)
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("compact_context", compact_context_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("ask_human", ask_human_node)
    graph.add_node("confirm_resolution", confirm_resolution_node)
    graph.add_node("retry_tool_call", retry_tool_call_node)

    # Entry point
    graph.set_entry_point("gather_context")

    # Edges: gather_context → planner → main_agent
    graph.add_edge("gather_context", "planner")
    graph.add_edge("planner", "main_agent")
    graph.add_conditional_edges(
        "main_agent",
        route_decision,
        {
            "continue": "tools",
            "need_approval": "human_approval",
            "ask_human": "ask_human",
            "retry_tool_call": "retry_tool_call",
            "complete": "confirm_resolution",
        },
    )
    graph.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "compact_context": "compact_context",
            "main_agent": "main_agent",
        },
    )
    graph.add_edge("compact_context", "main_agent")
    graph.add_edge("retry_tool_call", "main_agent")
    graph.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {
            "tools": "tools",
            "main_agent": "main_agent",
        },
    )
    graph.add_edge("ask_human", "main_agent")
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
        interrupt_before=["human_approval", "ask_human", "confirm_resolution"],
    )
