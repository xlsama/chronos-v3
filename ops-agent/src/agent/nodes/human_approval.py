from langchain_core.messages import ToolMessage

from src.agent.state import OpsState


async def human_approval_node(state: OpsState) -> dict:
    """This node is an interrupt point.
    LangGraph will pause here until the user approves/rejects.
    The approval logic is handled externally via the checkpoint resume mechanism.
    """
    last_message = state["messages"][-1]
    write_calls = [
        tc for tc in last_message.tool_calls if tc["name"] == "exec_write_tool"
    ]

    return {
        "needs_approval": True,
        "pending_tool_call": write_calls[0] if write_calls else None,
    }
