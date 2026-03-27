"""子 Agent 图：验证单个假设的独立 LangGraph 图。"""

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.ops_agent.nodes.investigation_agent import (
    build_investigation_tools,
    investigation_agent_node,
    route_investigation_decision,
)
from src.ops_agent.state import InvestigationState


def route_after_investigation_approval(state: InvestigationState) -> str:
    """审批后路由：批准→tools，拒绝→investigation_agent。"""
    decision = state.get("approval_decision", "approved")
    return "investigation_agent" if decision in ("rejected", "supplemented") else "tools"


def build_investigation_graph():
    """构建子 Agent 图。"""
    tools = build_investigation_tools()
    tool_node = ToolNode(tools)

    graph = StateGraph(InvestigationState)

    # 复用主图的 human_approval 和 ask_human 节点逻辑，但适配 InvestigationState
    from src.ops_agent.nodes.investigation_nodes import (
        investigation_ask_human_node,
        investigation_human_approval_node,
        investigation_retry_tool_call_node,
    )

    graph.add_node("investigation_agent", investigation_agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("human_approval", investigation_human_approval_node)
    graph.add_node("ask_human", investigation_ask_human_node)
    graph.add_node("retry_tool_call", investigation_retry_tool_call_node)

    graph.set_entry_point("investigation_agent")

    graph.add_conditional_edges(
        "investigation_agent",
        route_investigation_decision,
        {
            "continue": "tools",
            "need_approval": "human_approval",
            "ask_human": "ask_human",
            "retry_tool_call": "retry_tool_call",
            "complete": END,
        },
    )
    graph.add_edge("tools", "investigation_agent")
    graph.add_conditional_edges(
        "human_approval",
        route_after_investigation_approval,
        {
            "tools": "tools",
            "investigation_agent": "investigation_agent",
        },
    )
    graph.add_edge("ask_human", "investigation_agent")
    graph.add_edge("retry_tool_call", "investigation_agent")

    return graph


def compile_investigation_graph(checkpointer=None):
    """编译子 Agent 图，带中断点。"""
    graph = build_investigation_graph()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approval", "ask_human"],
    )
