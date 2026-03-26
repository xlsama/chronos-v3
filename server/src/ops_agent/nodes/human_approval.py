from langchain_core.messages import ToolMessage

from src.lib.logger import get_logger
from src.ops_agent.state import OpsState

_APPROVAL_TOOLS = {"ssh_bash", "bash", "service_exec"}


async def human_approval_node(state: OpsState) -> dict:
    """This node is an interrupt point (interrupt_before).

    With interrupt_before, the graph pauses BEFORE this node runs.
    On resume, Command(update={"approval_decision": ...}) sets the decision,
    then this node runs for the first time.

    We check approval_decision FIRST so that the decision set by Command(update=...)
    is processed immediately, injecting ToolMessages before routing continues.
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="approval", sid=sid)

    decision = state.get("approval_decision")

    if decision:
        # Decision set by Command(update=...) on resume
        log.info("Resume", decision=decision)

        if decision in ("rejected", "supplemented"):
            # Inject a ToolMessage telling the LLM the command was rejected
            supplement = state.get("approval_supplement")
            if decision == "supplemented" and supplement:
                content = (
                    f"用户拒绝了该命令并补充说明: {supplement}\n请根据用户的补充信息重新思考方案。"
                )
            else:
                content = "用户拒绝了该命令，请换一个方案继续排查。"

            last_message = state["messages"][-1]
            tool_messages = []
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                for tc in last_message.tool_calls:
                    if tc["name"] in _APPROVAL_TOOLS:
                        tool_messages.append(
                            ToolMessage(
                                content=content,
                                tool_call_id=tc["id"],
                            )
                        )
            log.info(
                "Rejected",
                decision=decision,
                has_supplement=bool(supplement),
                injected_messages=len(tool_messages),
            )
            # Keep approval_decision so route_after_approval can read it;
            # next Command(update=...) will overwrite it.
            return {
                "messages": tool_messages,
                "needs_approval": False,
                "pending_tool_call": None,
                "approval_supplement": None,
            }

        # Approved: clear approval state, continue to tools
        log.info("Approved")
        return {
            "needs_approval": False,
            "pending_tool_call": None,
            "approval_decision": None,
            "approval_supplement": None,
        }

    # No decision yet: initial entry, extract pending tool call for UI display
    last_message = state["messages"][-1]
    approval_calls = [tc for tc in last_message.tool_calls if tc["name"] in _APPROVAL_TOOLS]

    for tc in approval_calls:
        cmd_preview = tc.get("args", {}).get("command", "")[:200]
        log.info("Pending tool", tool=tc["name"], command=cmd_preview)

    log.info("Initial entry", pending_approval_calls=len(approval_calls))

    return {
        "needs_approval": True,
        "pending_tool_call": approval_calls[0] if approval_calls else None,
    }
