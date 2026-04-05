"""主图 —— 统一路径架构：所有意图走同一管线，intent 影响 triage/plan 行为。"""

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.ops_agent.nodes.ask_human import ask_human_node
from src.ops_agent.nodes.compact_node import main_compact_node
from src.ops_agent.nodes.gather_context import gather_context_node
from src.ops_agent.nodes.intent_classify import intent_classify_node
from src.ops_agent.nodes.interrupt_nodes import (
    agent_approval_node,
    agent_ask_human_node,
    confirm_resolution_node,
    main_retry_node,
    parallel_agent_approval_node,
    parallel_agent_ask_human_node,
    route_after_agent,
    route_after_parallel_agents,
    route_after_resolution,
    route_after_verification,
    verification_approval_node,
    verification_ask_human_node,
)
from src.ops_agent.nodes.main_agent import (
    main_agent_node,
    route_main_decision,
)
from src.ops_agent.nodes.parallel_agent_runner import run_parallel_agents_node
from src.ops_agent.nodes.plan import plan_node
from src.ops_agent.nodes.agent_runner import run_agent_node
from src.ops_agent.nodes.triage import triage_node
from src.ops_agent.nodes.verification_runner import run_verification_node
from src.ops_agent.state import MainState
from src.ops_agent.tools.registry import build_tools_for_agent


def build_graph():
    # --- 主 Agent 工具 ---
    all_main_tools = build_tools_for_agent("main")
    main_regular_tools = [
        t
        for t in all_main_tools
        if t.name not in (
            "spawn_agent", "spawn_parallel_agents",
            "spawn_verification", "complete", "ask_human",
        )
    ]
    main_tool_node = ToolNode(main_regular_tools)

    graph = StateGraph(MainState)

    # === 入口：意图分类 ===
    graph.add_node("intent_classify", intent_classify_node)
    graph.set_entry_point("intent_classify")

    # === 统一路径（所有意图共用）===
    graph.add_node("gather_context", gather_context_node)
    graph.add_node("triage", triage_node)
    graph.add_node("plan", plan_node)
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("tools", main_tool_node)
    graph.add_node("run_agent", run_agent_node)
    graph.add_node("run_parallel_agents", run_parallel_agents_node)
    graph.add_node("confirm_resolution", confirm_resolution_node)
    graph.add_node("agent_approval", agent_approval_node)
    graph.add_node("agent_ask_human", agent_ask_human_node)
    graph.add_node("parallel_agent_approval", parallel_agent_approval_node)
    graph.add_node("parallel_agent_ask_human", parallel_agent_ask_human_node)
    graph.add_node("run_verification", run_verification_node)
    graph.add_node("verification_approval", verification_approval_node)
    graph.add_node("verification_ask_human", verification_ask_human_node)
    graph.add_node("ask_human", ask_human_node)
    graph.add_node("retry_tool_call", main_retry_node)
    graph.add_node("compact", main_compact_node)

    # === 意图路由 → 统一走 gather_context ===
    graph.add_edge("intent_classify", "gather_context")

    # === 主管线 ===
    graph.add_edge("gather_context", "triage")
    graph.add_edge("triage", "plan")
    graph.add_edge("plan", "main_agent")

    graph.add_conditional_edges(
        "main_agent",
        route_main_decision,
        {
            "spawn_agent": "run_agent",
            "spawn_parallel": "run_parallel_agents",
            "spawn_verification": "run_verification",
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

    # === Investigation Sub-Agent ===
    graph.add_conditional_edges(
        "run_agent",
        route_after_agent,
        {
            "main_agent": "main_agent",
            "agent_approval": "agent_approval",
            "agent_ask_human": "agent_ask_human",
        },
    )
    graph.add_edge("agent_approval", "run_agent")
    graph.add_edge("agent_ask_human", "run_agent")

    # === Parallel Investigation Sub-Agents ===
    graph.add_conditional_edges(
        "run_parallel_agents",
        route_after_parallel_agents,
        {
            "main_agent": "main_agent",
            "parallel_agent_approval": "parallel_agent_approval",
            "parallel_agent_ask_human": "parallel_agent_ask_human",
        },
    )
    graph.add_edge("parallel_agent_approval", "run_parallel_agents")
    graph.add_edge("parallel_agent_ask_human", "run_parallel_agents")

    # === Verification Sub-Agent ===
    graph.add_conditional_edges(
        "run_verification",
        route_after_verification,
        {
            "confirm_resolution": "confirm_resolution",
            "main_agent": "main_agent",
            "verification_approval": "verification_approval",
            "verification_ask_human": "verification_ask_human",
        },
    )
    graph.add_edge("verification_approval", "run_verification")
    graph.add_edge("verification_ask_human", "run_verification")

    graph.add_edge("retry_tool_call", "main_agent")

    # === 结论确认 ===
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
            "agent_approval",
            "agent_ask_human",
            "parallel_agent_approval",
            "parallel_agent_ask_human",
            "verification_approval",
            "confirm_resolution",
        ],
    )
