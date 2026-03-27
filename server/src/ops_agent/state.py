from typing import TypedDict

from langgraph.graph import MessagesState


class HypothesisResult(TypedDict):
    hypothesis_id: str  # "H1", "H2", "H3"
    hypothesis_desc: str
    status: str  # "confirmed" | "eliminated" | "inconclusive"
    summary: str  # 子 Agent 的排查发现摘要
    evidence: str  # 关键证据
    action_taken: str  # 执行的修复操作及验证结果，未修复时为空字符串


class CoordinatorState(MessagesState):
    incident_id: str
    description: str
    severity: str
    is_complete: bool

    # 上下文（来自 gather_context）
    incident_history_summary: str | None
    kb_summary: str | None
    kb_project_ids: list[str]

    # 假设管理
    hypotheses: list[dict]  # [{id: "H1", desc: "...", priority: 1}, ...]
    current_hypothesis_index: int
    hypothesis_results: list[HypothesisResult]

    # 子 Agent 状态
    active_sub_agent_thread_id: str | None
    sub_agent_status: str | None  # "running" | "waiting_for_human" | "completed"

    # 子 Agent 恢复信息（interrupt 恢复时需要）
    active_hypothesis_id: str | None
    active_hypothesis_desc: str | None
    pending_launch_tool_call_id: str | None  # launch_investigation 的 tool_call_id

    # 审批透传（子 Agent interrupt 时传递到主图）
    needs_approval: bool
    pending_tool_call: dict | None
    approval_decision: str | None
    approval_supplement: str | None
    pending_approval_id: str | None  # 子 Agent 审批的 ApprovalRequest ID

    # coordinator retry
    tool_call_retry_count: int


class InvestigationState(MessagesState):
    incident_id: str
    description: str
    severity: str
    hypothesis_id: str
    hypothesis_desc: str
    prior_findings: str  # 之前子 Agent 的发现
    kb_summary: str | None
    is_complete: bool
    needs_approval: bool
    pending_tool_call: dict | None
    approval_decision: str | None
    approval_supplement: str | None
    ask_human_count: int
    tool_call_retry_count: int
