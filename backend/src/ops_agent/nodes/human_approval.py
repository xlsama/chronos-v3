from langchain_core.messages import ToolMessage

from src.ops_agent.state import OpsState


async def human_approval_node(state: OpsState) -> dict:
    """This node is an interrupt point.
    LangGraph will pause here until the user approves/rejects.
    The approval logic is handled externally via the checkpoint resume mechanism.

    On initial entry (before interrupt): sets needs_approval + pending_tool_call.
    On resume (after interrupt): checks approval_decision to route accordingly.
    """
    if state.get("needs_approval"):
        # Resume path: check approval decision
        decision = state.get("approval_decision")

        if decision == "rejected":
            # Inject a ToolMessage telling the LLM the command was rejected
            last_message = state["messages"][-1]
            tool_messages = []
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                for tc in last_message.tool_calls:
                    if tc["name"] == "bash":
                        tool_messages.append(
                            ToolMessage(
                                content="用户拒绝了该命令，请换一个方案继续排查。",
                                tool_call_id=tc["id"],
                            )
                        )
            return {
                "messages": tool_messages,
                "needs_approval": False,
                "pending_tool_call": None,
                "approval_decision": None,
            }

        # Approved: clear approval state, continue to tools
        return {
            "needs_approval": False,
            "pending_tool_call": None,
            "approval_decision": None,
        }

    # Initial entry: extract pending bash tool call
    last_message = state["messages"][-1]
    bash_calls = [
        tc for tc in last_message.tool_calls if tc["name"] == "bash"
    ]

    return {
        "needs_approval": True,
        "pending_tool_call": bash_calls[0] if bash_calls else None,
    }
