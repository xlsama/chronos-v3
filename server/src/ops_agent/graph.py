"""协调者图 —— 管理假设调度和子 Agent 执行。"""

from langgraph.graph import END, StateGraph

from src.lib.logger import get_logger
from src.ops_agent.nodes.gather_context import gather_context_node
from src.ops_agent.nodes.hypothesis_router import hypothesis_router_node, route_after_hypothesis
from src.ops_agent.nodes.planner import planner_node
from src.ops_agent.nodes.run_sub_agent import run_sub_agent_node
from src.ops_agent.nodes.synthesize import synthesize_node
from src.ops_agent.state import CoordinatorState


async def confirm_resolution_node(state: CoordinatorState) -> dict:
    """确认解决节点 —— 适配 CoordinatorState。"""
    from langchain_core.messages import HumanMessage
    from langgraph.types import interrupt

    sid = state["incident_id"][:8]
    log = get_logger(component="confirm_resolution", sid=sid)
    log.info("Waiting for user confirmation")
    user_response = interrupt({"type": "confirm_resolution"})
    log.info("User responded", response=str(user_response)[:100])

    if user_response == "confirmed":
        log.info("User confirmed resolution")
        return {"is_complete": True}

    log.info("User wants to continue investigation")
    return {
        "messages": [HumanMessage(content=f"用户表示问题未解决: {user_response}")],
        "is_complete": False,
    }


def route_after_resolution(state: CoordinatorState) -> str:
    log = get_logger(component="confirm_resolution", sid=state["incident_id"][:8])
    result = "end" if state.get("is_complete") else "hypothesis_router"
    log.info("route_after_resolution", route=result)
    return result


async def sub_agent_approval_node(state: CoordinatorState) -> dict:
    """透传节点 —— 仅用于触发 interrupt_before，让 AgentRunner 发布审批事件。

    恢复后，审批决定通过 Command(update=...) 传入 CoordinatorState，
    然后路由回 run_sub_agent 恢复子 Agent。
    """
    from langgraph.types import interrupt

    sid = state["incident_id"][:8]
    log = get_logger(component="sub_agent_approval", sid=sid)
    log.info("Sub-agent approval interrupt")
    # interrupt 等待审批决定
    interrupt({"type": "sub_agent_approval"})
    log.info("Sub-agent approval resumed")
    return {}


async def sub_agent_ask_human_node(state: CoordinatorState) -> dict:
    """透传节点 —— 仅用于触发 interrupt_before，让 AgentRunner 发布 ask_human 事件。"""
    from langchain_core.messages import HumanMessage
    from langgraph.types import interrupt

    sid = state["incident_id"][:8]
    log = get_logger(component="sub_agent_ask_human", sid=sid)
    log.info("Sub-agent ask_human interrupt")
    user_response = interrupt({"type": "sub_agent_ask_human"})
    log.info("Sub-agent ask_human resumed")
    # 将用户回复添加到消息中，run_sub_agent 恢复时会从中获取
    return {"messages": [HumanMessage(content=str(user_response))]}


def route_after_sub_agent_approval(state: CoordinatorState) -> str:
    """审批透传节点之后，路由回 run_sub_agent 恢复子 Agent。"""
    return "run_sub_agent"


def route_after_sub_agent_ask_human(state: CoordinatorState) -> str:
    """ask_human 透传节点之后，路由回 run_sub_agent 恢复子 Agent。"""
    return "run_sub_agent"


def build_graph():
    graph = StateGraph(CoordinatorState)

    # 节点
    graph.add_node("gather_context", gather_context_node)
    graph.add_node("planner", planner_node)
    graph.add_node("hypothesis_router", hypothesis_router_node)
    graph.add_node("run_sub_agent", run_sub_agent_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("confirm_resolution", confirm_resolution_node)
    graph.add_node("sub_agent_approval", sub_agent_approval_node)
    graph.add_node("sub_agent_ask_human", sub_agent_ask_human_node)

    # 入口
    graph.set_entry_point("gather_context")

    # 边
    graph.add_edge("gather_context", "planner")
    graph.add_edge("planner", "hypothesis_router")

    graph.add_conditional_edges(
        "hypothesis_router",
        route_after_hypothesis,
        {
            "run_sub_agent": "run_sub_agent",
            "synthesize": "synthesize",
            "sub_agent_approval": "sub_agent_approval",
            "sub_agent_ask_human": "sub_agent_ask_human",
        },
    )

    # run_sub_agent 完成后回到 hypothesis_router 决定下一步
    graph.add_edge("run_sub_agent", "hypothesis_router")

    # 审批/ask_human 透传节点恢复后回到 run_sub_agent
    graph.add_edge("sub_agent_approval", "run_sub_agent")
    graph.add_edge("sub_agent_ask_human", "run_sub_agent")

    # synthesize → confirm_resolution
    graph.add_edge("synthesize", "confirm_resolution")

    graph.add_conditional_edges(
        "confirm_resolution",
        route_after_resolution,
        {
            "end": END,
            "hypothesis_router": "hypothesis_router",
        },
    )

    return graph


def compile_graph(checkpointer=None):
    graph = build_graph()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["sub_agent_approval", "sub_agent_ask_human", "confirm_resolution"],
    )
