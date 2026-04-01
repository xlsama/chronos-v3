"""主图 —— Route-First 架构：意图分类 → incident/question/task 分流。"""

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.ops_agent.nodes.ask_human import ask_human_node
from src.ops_agent.nodes.compact_node import main_compact_node
from src.ops_agent.nodes.gather_context import gather_context_node
from src.ops_agent.nodes.intent_classify import intent_classify_node
from src.ops_agent.nodes.interrupt_nodes import (
    confirm_resolution_node,
    main_retry_node,
    qa_approval_node,
    qa_retry_node,
    route_after_classify,
    route_after_resolution,
    route_after_sub_agent,
    sub_agent_approval_node,
    sub_agent_ask_human_node,
)
from src.ops_agent.nodes.main_agent import (
    main_agent_node,
    route_main_decision,
)
from src.ops_agent.nodes.plan import plan_node
from src.ops_agent.nodes.triage import triage_node
from src.ops_agent.nodes.qa_agent import (
    build_qa_tools,
    qa_agent_node,
    route_qa_decision,
)
from src.ops_agent.nodes.sub_agent_lifecycle import run_sub_agent_node
from src.ops_agent.state import MainState
from src.ops_agent.tools.registry import build_tools_for_agent


def build_graph():
    # --- incident 路径工具 ---
    all_main_tools = build_tools_for_agent("main")
    main_regular_tools = [
        t for t in all_main_tools if t.name not in ("launch_investigation", "complete", "ask_human")
    ]
    main_tool_node = ToolNode(main_regular_tools)

    # --- QA 路径工具 ---
    all_qa_tools = build_qa_tools()
    qa_regular_tools = [t for t in all_qa_tools if t.name not in ("complete", "ask_human")]
    qa_tool_node = ToolNode(qa_regular_tools)

    graph = StateGraph(MainState)

    # === 入口：意图分类 ===
    graph.add_node("intent_classify", intent_classify_node)
    graph.set_entry_point("intent_classify")

    # === QA/Task 路径 ===
    graph.add_node("gather_context_qa", gather_context_node)  # 复用，但会跳过 history
    graph.add_node("qa_agent", qa_agent_node)
    graph.add_node("qa_tools", qa_tool_node)
    graph.add_node("qa_ask_human", ask_human_node)
    graph.add_node("qa_retry", qa_retry_node)
    graph.add_node("qa_approval", qa_approval_node)

    # === Incident 路径 ===
    graph.add_node("gather_context", gather_context_node)
    graph.add_node("triage", triage_node)
    graph.add_node("plan", plan_node)
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("tools", main_tool_node)
    graph.add_node("run_sub_agent", run_sub_agent_node)
    graph.add_node("confirm_resolution", confirm_resolution_node)
    graph.add_node("sub_agent_approval", sub_agent_approval_node)
    graph.add_node("sub_agent_ask_human", sub_agent_ask_human_node)
    graph.add_node("ask_human", ask_human_node)
    graph.add_node("retry_tool_call", main_retry_node)
    graph.add_node("compact", main_compact_node)

    # === 意图路由 ===
    graph.add_conditional_edges(
        "intent_classify",
        route_after_classify,
        {
            "gather_context_qa": "gather_context_qa",
            "gather_context": "gather_context",
        },
    )

    # === QA 路径边 ===
    graph.add_edge("gather_context_qa", "qa_agent")

    graph.add_conditional_edges(
        "qa_agent",
        route_qa_decision,
        {
            "qa_tools": "qa_tools",
            "qa_complete": END,
            "qa_ask_human": "qa_ask_human",
            "qa_retry": "qa_retry",
            "qa_approval": "qa_approval",
        },
    )

    graph.add_edge("qa_tools", "qa_agent")
    graph.add_edge("qa_ask_human", "qa_agent")
    graph.add_edge("qa_retry", "qa_agent")
    graph.add_edge("qa_approval", "qa_agent")

    # === Incident 路径边 ===
    graph.add_edge("gather_context", "triage")
    graph.add_edge("triage", "plan")
    graph.add_edge("plan", "main_agent")

    graph.add_conditional_edges(
        "main_agent",
        route_main_decision,
        {
            "launch_investigation": "run_sub_agent",
            "continue": "tools",
            "complete": "confirm_resolution",
            "ask_human": "ask_human",
            "retry_tool_call": "retry_tool_call",
            "compact": "compact",
        },
    )

    graph.add_edge("tools", "main_agent")
    graph.add_edge("ask_human", "main_agent")
    graph.add_edge("compact", "main_agent")

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
        interrupt_before=[
            "sub_agent_approval",
            "sub_agent_ask_human",
            "confirm_resolution",
            "qa_approval",
        ],
    )
