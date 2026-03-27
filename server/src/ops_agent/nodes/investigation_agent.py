"""子 Agent 的 LLM 节点 —— 专注验证单个假设。"""

import time

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.prompts.investigation_agent import INVESTIGATION_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import InvestigationState
from src.ops_agent.tools.ssh_bash_tool import list_servers as _list_servers
from src.ops_agent.tools.ssh_bash_tool import ssh_bash as _ssh_bash
from src.ops_agent.tools.bash_tool import local_bash as _local_bash
from src.ops_agent.tools.service_exec_tool import (
    list_services as _list_services,
    service_exec as _service_exec,
)
from src.ops_agent.tools.tool_classifier import CommandType, ServiceSafety, ShellSafety
from src.services.skill_service import SkillService


def _build_skills_context(skill_service: SkillService) -> str:
    """构建精简的 skills 上下文。"""
    available = skill_service.get_available_skills()
    if not available:
        return ""
    lines = ["\n<available_skills>"]
    for s in available:
        lines.append(f'  <skill name="{s["slug"]}">{s["description"]}</skill>')
    lines.append("</available_skills>")
    return "\n".join(lines)


def build_investigation_tools():
    """构建子 Agent 的工具集。"""
    from langchain_core.tools import tool

    @tool
    async def ssh_bash(server_id: str, command: str, explanation: str = "") -> dict:
        """在目标服务器执行 Shell 命令（通过 SSH）。
        系统自动判断命令权限：只读命令直接执行，写操作需人工审批。
        - server_id: 必须是 list_servers() 返回的有效 UUID
        - command: 要执行的 Shell 命令
        - explanation: 可选，写操作时提供操作说明
        """
        return await _ssh_bash(server_id=server_id, command=command)

    @tool
    async def bash(command: str, explanation: str = "") -> dict:
        """在本地执行命令（docker/kubectl/systemctl/curl 等）。
        - command: 要执行的命令
        - explanation: 可选，写操作时提供操作说明
        """
        return await _local_bash(command=command)

    @tool
    async def service_exec(service_id: str, command: str, explanation: str = "") -> str:
        """直连服务执行命令（PostgreSQL/MySQL/Redis/Prometheus 等）。
        - service_id: 必须是 list_services() 返回的有效 UUID
        - command: 要执行的命令/查询
        - explanation: 可选，写操作时提供操作说明
        """
        return await _service_exec(service_id=service_id, command=command)

    @tool
    async def list_servers() -> list[dict] | str:
        """列出所有可用服务器。返回 id, name, host, status。"""
        result = await _list_servers()
        if not result:
            return "当前没有注册任何服务器。"
        return result

    @tool
    async def list_services() -> list[dict] | str:
        """列出所有可用服务。返回 id, name, service_type, host, port, status。"""
        result = await _list_services()
        if not result:
            return "当前没有注册任何服务。"
        return result

    @tool
    def ask_human(question: str) -> str:
        """缺少关键信息时向用户提问。question 应简短精练（1-3行）。"""
        return question

    @tool
    def read_skill(path: str) -> str:
        """读取技能文件。"?" 列出所有可用技能，"slug" 读 SKILL.md，"slug/scripts/x.sh" 读脚本。"""
        service = SkillService()
        if path.strip() == "?":
            available = service.get_available_skills()
            if not available:
                return "当前没有可用技能。"
            lines = ["所有可用技能:"]
            for s in available:
                lines.append(f"- {s['slug']}: {s['description']}")
            return "\n".join(lines)
        parts = path.split("/", 1)
        slug = parts[0]
        rel_path = parts[1] if len(parts) > 1 else None
        try:
            return service.read_file(slug, rel_path)
        except FileNotFoundError:
            return f"未找到: {path}"

    @tool
    def report_findings(status: str, summary: str, evidence: str) -> str:
        """调查完成后调用，报告本次调查结果。
        - status: "confirmed"（假设成立）/ "eliminated"（假设排除）/ "inconclusive"（证据不足）
        - summary: 简要说明发现了什么（1-3 句话）
        - evidence: 关键证据（命令输出、日志片段等关键内容）
        """
        return f"调查结果已记录: status={status}, summary={summary}"

    return [
        ssh_bash,
        bash,
        service_exec,
        list_servers,
        list_services,
        read_skill,
        ask_human,
        report_findings,
    ]


def _get_investigation_llm():
    s = get_settings()
    return ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )


def _log_retry(retry_state):
    get_logger(component="investigation").warning(
        "LLM call failed, retrying",
        attempt=retry_state.attempt_number,
        error=str(retry_state.outcome.exception()),
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
    before_sleep=_log_retry,
)
async def _invoke_llm_with_retry(llm, messages):
    return await llm.ainvoke(messages)


def _sanitize_llm_response(response: AIMessage, valid_tool_names: set[str]) -> AIMessage:
    """Strip invalid tool_calls when the model hallucinates an unknown tool."""
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    unknown = [tc for tc in tool_calls if str(tc.get("name", "")).strip() not in valid_tool_names]
    if not unknown:
        return response
    get_logger(component="investigation").warning(
        "Stripping unknown tool calls",
        tools=[tc.get("name") for tc in unknown],
    )
    return AIMessage(content=response.content or "")


async def investigation_agent_node(state: InvestigationState) -> dict:
    """子 Agent LLM 节点：验证单个假设。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="investigation", sid=sid)

    tools = build_investigation_tools()
    llm = _get_investigation_llm().bind_tools(tools)

    # 构建 prior_findings 上下文
    prior_findings = state.get("prior_findings", "")
    prior_context = ""
    if prior_findings:
        prior_context = f"## 之前的调查发现\n\n{prior_findings}"

    kb_summary = state.get("kb_summary")
    kb_context = f"## 项目知识库上下文\n{kb_summary}" if kb_summary else ""

    skill_service = SkillService()
    skills_context = _build_skills_context(skill_service)

    system_prompt = INVESTIGATION_AGENT_SYSTEM_PROMPT.format(
        hypothesis_id=state["hypothesis_id"],
        hypothesis_desc=state["hypothesis_desc"],
        description=state["description"],
        severity=state["severity"],
        prior_findings_context=prior_context,
        kb_context=kb_context,
        skills_context=skills_context,
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    tool_names = [t.name for t in tools]
    log.info(
        "investigation_agent_node invoked",
        hypothesis=state["hypothesis_id"],
        messages=len(messages),
    )

    t0 = time.monotonic()
    response = await _invoke_llm_with_retry(llm, messages)
    elapsed = time.monotonic() - t0
    log.info("LLM responded", elapsed=f"{elapsed:.2f}s")

    safe_response = _sanitize_llm_response(response, set(tool_names))
    return {"messages": [safe_response]}


async def _get_service_type(service_id: str) -> str:
    """Lookup service_type for a given service_id."""
    if not service_id:
        return ""
    try:
        from src.db.connection import get_session_factory
        from src.db.models import Service
        import uuid as _uuid

        async with get_session_factory()() as session:
            svc = await session.get(Service, _uuid.UUID(service_id))
            return svc.service_type if svc else ""
    except Exception:
        return ""


async def route_investigation_decision(state: InvestigationState) -> str:
    """路由子 Agent 的下一步。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="investigation", sid=sid)
    last_message = state["messages"][-1]
    tools = build_investigation_tools()
    valid_tool_names = {t.name for t in tools}

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        if state.get("ask_human_count", 0) >= 5:
            log.warning("ask_human count exceeded, forcing complete")
            return "complete"

        max_retries = get_settings().tool_call_max_retries
        retry_count = state.get("tool_call_retry_count", 0)
        if retry_count >= max_retries:
            log.info("no tool_calls after retries -> ask_human")
            return "ask_human"

        log.info("no tool_calls -> retry_tool_call")
        return "retry_tool_call"

    for tc in last_message.tool_calls:
        name = tc["name"]
        if name not in valid_tool_names:
            log.warning("unknown tool -> ask_human", tool=name)
            return "ask_human"
        if name == "report_findings":
            log.info("tool=report_findings -> complete")
            return "complete"
        if name == "ask_human":
            if state.get("ask_human_count", 0) >= 5:
                log.warning("ask_human count exceeded, forcing complete")
                return "complete"
            log.info("tool=ask_human -> ask_human")
            return "ask_human"
        if name in ("ssh_bash", "bash"):
            cmd_type = ShellSafety.classify(tc["args"].get("command", ""), local=(name == "bash"))
            if cmd_type in (CommandType.WRITE, CommandType.DANGEROUS, CommandType.BLOCKED):
                log.info("need_approval", tool=name, cmd_type=cmd_type.name)
                return "need_approval"
        if name == "service_exec":
            service_type = await _get_service_type(tc["args"].get("service_id", ""))
            cmd_type = ServiceSafety.classify(service_type, tc["args"].get("command", ""))
            if cmd_type in (CommandType.WRITE, CommandType.DANGEROUS, CommandType.BLOCKED):
                log.info("need_approval", tool="service_exec", cmd_type=cmd_type.name)
                return "need_approval"

    log.info("-> continue")
    return "continue"
