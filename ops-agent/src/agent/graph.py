from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent.nodes.human_approval import human_approval_node
from src.agent.nodes.main_agent import build_tools, main_agent_node, route_decision
from src.agent.nodes.summarize import summarize_node
from src.agent.state import OpsState


def build_graph():
    tools = build_tools()
    tool_node = ToolNode(tools)

    graph = StateGraph(OpsState)

    # Add nodes
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("summarize", summarize_node)

    # Entry point
    graph.set_entry_point("main_agent")

    # Edges
    graph.add_conditional_edges(
        "main_agent",
        route_decision,
        {
            "continue": "tools",
            "need_approval": "human_approval",
            "complete": "summarize",
        },
    )
    graph.add_edge("tools", "main_agent")
    graph.add_edge("human_approval", "tools")
    graph.add_edge("summarize", END)

    return graph


def compile_graph(checkpointer=None):
    graph = build_graph()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approval"],
    )
