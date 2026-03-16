from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.ops_agent.nodes.ask_human import ask_human_node
from src.ops_agent.nodes.discover_project import discover_project_node
from src.ops_agent.nodes.gather_context import gather_context_node
from src.ops_agent.nodes.human_approval import human_approval_node
from src.ops_agent.nodes.main_agent import build_all_tools, main_agent_node, route_decision
from src.ops_agent.nodes.summarize import summarize_node
from src.ops_agent.state import OpsState


def build_graph():
    # ToolNode gets ALL tools (including conditional ones)
    all_tools = build_all_tools()
    tool_node = ToolNode(all_tools)

    graph = StateGraph(OpsState)

    # Add nodes
    graph.add_node("discover_project", discover_project_node)
    graph.add_node("gather_context", gather_context_node)
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("ask_human", ask_human_node)
    graph.add_node("summarize", summarize_node)

    # Entry point
    graph.set_entry_point("discover_project")

    # Edges
    graph.add_edge("discover_project", "gather_context")
    graph.add_edge("gather_context", "main_agent")
    graph.add_conditional_edges(
        "main_agent",
        route_decision,
        {
            "continue": "tools",
            "need_approval": "human_approval",
            "ask_human": "ask_human",
            "complete": "summarize",
        },
    )
    graph.add_edge("tools", "main_agent")
    graph.add_edge("human_approval", "tools")
    graph.add_edge("ask_human", "main_agent")
    graph.add_edge("summarize", END)

    return graph


def compile_graph(checkpointer=None):
    graph = build_graph()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approval", "ask_human"],
    )
