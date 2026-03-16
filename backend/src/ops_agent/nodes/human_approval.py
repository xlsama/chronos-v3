from src.ops_agent.state import OpsState


async def human_approval_node(state: OpsState) -> dict:
    """This node is an interrupt point.
    LangGraph will pause here until the user approves/rejects.
    The approval logic is handled externally via the checkpoint resume mechanism.

    On initial entry (before interrupt): sets needs_approval + pending_tool_call.
    On resume (after interrupt): clears approval state so graph continues to tools.
    """
    if state.get("needs_approval"):
        # Resume path: clear approval state (Gap D)
        return {
            "needs_approval": False,
            "pending_tool_call": None,
        }

    # Initial entry: extract pending write tool call
    last_message = state["messages"][-1]
    write_calls = [
        tc for tc in last_message.tool_calls if tc["name"] == "exec_write"
    ]

    return {
        "needs_approval": True,
        "pending_tool_call": write_calls[0] if write_calls else None,
    }
