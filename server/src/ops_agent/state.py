from langgraph.graph import MessagesState


class OpsState(MessagesState):
    incident_id: str
    description: str
    severity: str
    is_complete: bool
    needs_approval: bool
    pending_tool_call: dict | None
    approval_decision: str | None
    incident_history_summary: str | None
    kb_summary: str | None
    kb_project_id: str | None
    ask_human_count: int
    tool_call_retry_count: int
