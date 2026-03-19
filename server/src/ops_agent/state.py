from langgraph.graph import MessagesState


class OpsState(MessagesState):
    incident_id: str
    description: str
    severity: str
    is_complete: bool
    needs_approval: bool
    pending_tool_call: dict | None
    approval_decision: str | None
    summary_md: str | None
    incident_history_summary: str | None
    kb_summary: str | None
    ask_human_count: int
