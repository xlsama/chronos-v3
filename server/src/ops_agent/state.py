from typing import TypedDict

from langgraph.graph import MessagesState


class HypothesisResult(TypedDict):
    hypothesis_id: str  # "H1", "H2", "H3"
    hypothesis_desc: str
    status: str  # "confirmed" | "eliminated" | "inconclusive"
    summary: str  # 一句话结论（用于后续子 Agent 上下文）
    detail: str  # 结构化排查报告（含排查链路、关键证据、修复操作等）
    verification_evidence: str  # 验证证据（命令+输出，或无法验证的原因）


class ActiveAgent(TypedDict):
    """并行模式下每个子 Agent 的跟踪状态。"""

    thread_id: str
    hypothesis_id: str  # "H1"
    hypothesis_title: str
    hypothesis_desc: str
    status: str  # "completed" | "interrupted_approval" | "interrupted_ask_human" | "failed"
    result: HypothesisResult | None  # 完成时填充
    pending_tool_call: dict | None  # 审批中断时填充
    pending_approval_id: str | None


class MainState(MessagesState):
    incident_id: str
    description: str
    severity: str
    is_complete: bool

    # 意图分类
    intent: str | None  # "incident" | "question" | "task"

    # 上下文（来自 gather_context）
    incident_history_summary: str | None
    kb_summary: str | None
    kb_project_ids: list[str]

    # 假设管理
    hypothesis_results: list[HypothesisResult]

    # 子 Agent 状态
    active_agent_thread_id: str | None
    agent_status: str | None  # "running" | "waiting_for_human" | "completed"

    # 子 Agent 恢复信息（interrupt 恢复时需要）
    active_hypothesis_id: str | None
    active_hypothesis_title: str | None
    active_hypothesis_desc: str | None
    pending_spawn_tool_call_id: str | None  # spawn_agent 的 tool_call_id

    # 子 Agent ask_human 图片文件引用（避免通过 checkpoint 传 bytes）
    pending_human_images: list[dict] | None  # [{"filename","stored_filename","content_type"}]

    # 审批透传（子 Agent interrupt 时传递到主图）
    needs_approval: bool
    pending_tool_call: dict | None
    approval_decision: str | None
    approval_supplement: str | None
    pending_approval_id: str | None  # 子 Agent 审批的 ApprovalRequest ID

    # main agent
    ask_human_count: int
    tool_call_retry_count: int

    # compact
    compact_md: str | None
    needs_compact: bool

    # Verification Sub-Agent
    active_verification_thread_id: str | None
    verification_status: str | None  # "running" | "waiting_for_human" | "completed"
    pending_verify_tool_call_id: str | None  # spawn_verification 的 tool_call_id
    verification_report: dict | None  # VerificationReport

    # 并行子 Agent（与串行字段互不干扰）
    parallel_agents: list[ActiveAgent]
    parallel_launch_tool_call_id: str | None
    parallel_interrupted_agent_id: str | None  # 当前正在处理中断的子 Agent


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

    # compact
    compact_md: str | None
    needs_compact: bool


class VerificationState(MessagesState):
    incident_id: str
    description: str
    severity: str
    answer_md: str  # 待验证的排查结论
    hypothesis_results: list[HypothesisResult]  # investigation 发现
    kb_summary: str | None
    is_complete: bool
    needs_approval: bool
    pending_tool_call: dict | None
    approval_decision: str | None
    approval_supplement: str | None
    ask_human_count: int
    tool_call_retry_count: int

    # compact
    compact_md: str | None
    needs_compact: bool
