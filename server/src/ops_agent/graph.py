from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.lib.logger import logger
from src.ops_agent.nodes.ask_human import ask_human_node
from src.ops_agent.nodes.confirm_resolution import confirm_resolution_node, route_after_resolution
from src.ops_agent.nodes.gather_context import gather_context_node
from src.ops_agent.nodes.human_approval import human_approval_node
from src.ops_agent.nodes.main_agent import build_tools, main_agent_node, route_decision
from src.ops_agent.state import OpsState


def route_after_approval(state: OpsState) -> str:
    """Route after human_approval: rejected goes back to LLM, approved goes to tools."""
    sid = state["incident_id"][:8]
    decision = state.get("approval_decision", "approved")
    route = "main_agent" if decision == "rejected" else "tools"
    logger.info(f"[{sid}] [approval] route_after_approval: decision={decision} -> {route}")
    if decision == "rejected":
        return "main_agent"
    return "tools"


def build_graph():
    all_tools = build_tools()
    tool_node = ToolNode(all_tools)

    graph = StateGraph(OpsState)

    # Add nodes
    graph.add_node("gather_context", gather_context_node)
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("ask_human", ask_human_node)
    graph.add_node("confirm_resolution", confirm_resolution_node)

    # Entry point
    graph.set_entry_point("gather_context")

    # Edges
    graph.add_edge("gather_context", "main_agent")
    graph.add_conditional_edges(
        "main_agent",
        route_decision,
        {
            "continue": "tools",
            "need_approval": "human_approval",
            "ask_human": "ask_human",
            "complete": "confirm_resolution",
        },
    )
    graph.add_edge("tools", "main_agent")
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
