"""Verification Agent 图：验证排查结论的独立 LangGraph 图。"""

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.ops_agent.nodes.compact_node import verification_compact_node
from src.ops_agent.agents.verification_agent import (
    route_verification_decision,
    verification_agent_node,
)
from src.ops_agent.agents.verification_nodes import (
    verification_ask_human_node,
    verification_human_approval_node,
    verification_missing_explanation_node,
    verification_retry_tool_call_node,
)
from src.ops_agent.state import VerificationState
from src.ops_agent.tools.registry import build_tools_for_agent


def route_after_verification_approval(state: VerificationState) -> str:
    """审批后路由：批准→tools，拒绝→verification_agent。"""
    decision = state.get("approval_decision", "approved")
    return "verification_agent" if decision in ("rejected", "supplemented") else "tools"


def build_verification_graph():
    """构建 Verification Agent 图。"""
    tools = build_tools_for_agent("verification")
    tool_node = ToolNode(tools)

    graph = StateGraph(VerificationState)

    graph.add_node("verification_agent", verification_agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("human_approval", verification_human_approval_node)
    graph.add_node("ask_human", verification_ask_human_node)
    graph.add_node("retry_tool_call", verification_retry_tool_call_node)
    graph.add_node("missing_explanation", verification_missing_explanation_node)
    graph.add_node("compact", verification_compact_node)

    graph.set_entry_point("verification_agent")

    graph.add_conditional_edges(
        "verification_agent",
        route_verification_decision,
        {
            "continue": "tools",
            "need_approval": "human_approval",
            "missing_explanation": "missing_explanation",
            "ask_human": "ask_human",
            "retry_tool_call": "retry_tool_call",
            "compact": "compact",
            "complete": END,
        },
    )
    graph.add_edge("tools", "verification_agent")
    graph.add_conditional_edges(
        "human_approval",
        route_after_verification_approval,
        {
            "tools": "tools",
            "verification_agent": "verification_agent",
        },
    )
    graph.add_edge("ask_human", "verification_agent")
    graph.add_edge("retry_tool_call", "verification_agent")
    graph.add_edge("missing_explanation", "verification_agent")
    graph.add_edge("compact", "verification_agent")

    return graph


def compile_verification_graph(checkpointer=None):
    """编译 Verification Agent 图，带中断点。"""
    graph = build_verification_graph()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approval", "ask_human"],
    )
