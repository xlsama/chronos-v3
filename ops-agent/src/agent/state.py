import operator
import uuid
from typing import Annotated, Any

from langgraph.graph import MessagesState


class OpsState(MessagesState):
    incident_id: str
    infrastructure_id: str
    project_id: str
    title: str
    description: str
    severity: str
    is_complete: bool
    needs_approval: bool
    pending_tool_call: dict | None
    summary_md: str | None
