from langgraph.graph import MessagesState


class OpsState(MessagesState):
    incident_id: str
    description: str
    severity: str
    is_complete: bool
    needs_approval: bool
    pending_tool_call: dict | None
    approval_decision: str | None
    approval_supplement: str | None
    incident_history_summary: str | None
    kb_summary: str | None
    kb_project_ids: list[str]
    ask_human_count: int
    tool_call_retry_count: int

    # --- Context Manager ---
    investigation_summary: str | None
    message_count_at_last_compact: int
    compact_count: int

    # --- Evaluator ---
    evaluation_result: dict | None
    evaluation_attempts: int
