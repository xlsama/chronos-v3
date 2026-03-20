from langchain_core.messages import ToolMessage

from src.lib.logger import logger, ac
from src.ops_agent.state import OpsState

_APPROVAL_TOOLS = {"ssh_bash", "bash", "service_exec"}


async def human_approval_node(state: OpsState) -> dict:
    """This node is an interrupt point.
    LangGraph will pause here until the user approves/rejects.
    The approval logic is handled externally via the checkpoint resume mechanism.

    On initial entry (before interrupt): sets needs_approval + pending_tool_call.
    On resume (after interrupt): checks approval_decision to route accordingly.
    """
    sid = state["incident_id"][:8]

    if state.get("needs_approval"):
        # Resume path: check approval decision
        decision = state.get("approval_decision")
        logger.info(f"[{sid}] {ac('approval')} Resume: decision={decision}")

        if decision == "rejected":
            # Inject a ToolMessage telling the LLM the command was rejected
            last_message = state["messages"][-1]
            tool_messages = []
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                for tc in last_message.tool_calls:
                    if tc["name"] in _APPROVAL_TOOLS:
                        tool_messages.append(
                            ToolMessage(
                                content="用户拒绝了该命令，请换一个方案继续排查。",
                                tool_call_id=tc["id"],
                            )
                        )
            logger.info(f"[{sid}] {ac('approval')} Rejected: injected {len(tool_messages)} rejection message(s)")
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

    # Initial entry: extract pending tool call that needs approval
    last_message = state["messages"][-1]
    approval_calls = [
        tc for tc in last_message.tool_calls if tc["name"] in _APPROVAL_TOOLS
    ]

    for tc in approval_calls:
        cmd_preview = tc.get("args", {}).get("command", "")[:200]
        logger.info(f"\n[{sid}] {ac('approval')} Pending tool: {tc['name']}, command={cmd_preview}")

    logger.info(f"\n[{sid}] {ac('approval')} Initial entry: pending approval_calls={len(approval_calls)}")

    return {
        "needs_approval": True,
        "pending_tool_call": approval_calls[0] if approval_calls else None,
    }
