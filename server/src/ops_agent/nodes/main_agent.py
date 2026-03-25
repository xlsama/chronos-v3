import asyncio
import time

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.ops_agent.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import OpsState
from src.env import get_settings
from src.ops_agent.tools.ssh_bash_tool import ssh_bash as _ssh_bash, list_servers as _list_servers
from src.ops_agent.tools.bash_tool import local_bash as _local_bash
from src.ops_agent.tools.service_exec_tool import (
    service_exec as _service_exec,
    list_services as _list_services,
)
from src.ops_agent.tools.tool_permissions import ShellSafety, ServiceSafety, CommandType
from src.services.skill_service import SkillService
from src.lib.logger import get_logger


def build_tools():
    from langchain_core.tools import tool

    @tool
    async def ssh_bash(server_id: str, command: str, explanation: str = "") -> dict:
        """在目标服务器执行 Shell 命令（通过 SSH）。
        命令在 server_id 对应的远程主机上运行，不是在 agent 自身容器中运行。
        `localhost`、`127.0.0.1`、文件路径、监听端口都必须按目标服务器视角解释。
        系统自动判断命令权限：只读命令直接执行，写操作需人工审批。
        网络请求用 curl。查看日志/配置文件用 cat/tail/grep，但禁止通过 cat 源码或构建产物来获取数据库表结构、连接串等运行时信息——应使用 psql/mysql/redis-cli 等 CLI 直接查询。
        - server_id: 必须是 list_servers() 返回的有效 UUID
        - command: 要执行的 Shell 命令
        - explanation: 可选，写操作时提供操作说明（展示在审批卡片上）
        """
        return await _ssh_bash(server_id=server_id, command=command)

    @tool
    async def bash(command: str, explanation: str = "") -> dict:
        """在本地执行命令。可以执行 docker/kubectl/systemctl 等服务管理命令（写操作需审批）。
        用于不需要 SSH 到远程服务器的场景：运行本地脚本、curl 调用 API、docker/kubectl 管理容器和集群等。
        注意：禁止 sudo/su 提权命令。
        - command: 要执行的命令
        - explanation: 可选，写操作时提供操作说明
        """
        return await _local_bash(command=command)

    @tool
    async def service_exec(service_id: str, command: str, explanation: str = "") -> str:
        """直连服务执行命令。
        - PostgreSQL: 纯 SQL 语句（SELECT/INSERT/UPDATE 等，不支持 psql 元命令，需要表信息用 information_schema）
        - Redis: Redis 命令（GET/SET/INFO 等）
        - Prometheus: PromQL 表达式
        - service_id: 必须是 list_services() 返回的有效 UUID
        - command: 要执行的命令/查询
        - explanation: 可选，写操作时提供操作说明
        """
        return await _service_exec(service_id=service_id, command=command)

    @tool
    async def list_servers() -> list[dict] | str:
        """列出所有可用服务器。返回 id, name, host, status。
        用于发现目标服务器（SSH 远程执行）。
        如果返回空数组 `[]`，或明确提示“当前没有注册任何服务器”，表示当前没有已登记的 SSH 服务器资产，不是工具异常。
        """
        result = await _list_servers()
        if not result:
            return "当前没有注册任何服务器（servers 表为空）。无法使用 ssh_bash 工具。如需 SSH 远程排查，请通过 ask_human 请用户在「连接」页面添加服务器。"
        return result

    @tool
    async def list_services() -> list[dict] | str:
        """列出所有可用服务。返回 id, name, service_type, host, port, status。
        用于发现可直连的数据库/缓存/监控服务。
        """
        result = await _list_services()
        if not result:
            return "当前没有注册任何服务（services 表为空）。无法使用 service_exec 工具。如需数据库/缓存排查，请通过 ask_human 请用户在「连接」页面添加服务。"
        return result

    @tool
    def ask_human(question: str) -> str:
        """当你缺少关键信息无法继续排查时，向用户提问。
        question 应简短精练（1-3行），只写你需要用户回答的关键问题。
        分析推理写在思考过程中，不要放进 question。
        """
        return question

    @tool
    def read_skill(path: str) -> str:
        """读取技能文件。查看 <available_skills> 后，用此工具读取匹配技能。
        - "?" → 列出所有可用技能
        - "mysql-oom" → SKILL.md 内容 + 文件目录
        - "mysql-oom/scripts/check.sh" → 脚本内容
        """
        skill_log = get_logger(component="skill")
        service = SkillService()
        if path.strip() == "?":
            available = service.get_available_skills()
            if not available:
                skill_log.info("read_skill: no skills available", path=path)
                return "当前没有可用技能。"
            skill_log.info("read_skill: listing skills", path=path, count=len(available))
            lines = ["所有可用技能:"]
            for s in available:
                lines.append(f"- {s['slug']}: {s['description']}")
            return "\n".join(lines)
        parts = path.split("/", 1)
        slug = parts[0]
        rel_path = parts[1] if len(parts) > 1 else None
        try:
            content = service.read_file(slug, rel_path)
            skill_log.info("read_skill", slug=slug, rel_path=rel_path, content_len=len(content))
            skill_log.debug("read_skill content", content=content)
            return content
        except FileNotFoundError:
            skill_log.warning("read_skill: not found", path=path)
            return f"未找到: {path}"

    @tool
    def complete(answer_md: str) -> str:
        """排查完成后调用。answer_md 是给用户看的正式回答，要直面问题、给出结论和建议。"""
        return answer_md

    return [
        ssh_bash,
        bash,
        service_exec,
        list_servers,
        list_services,
        read_skill,
        ask_human,
        complete,
    ]


_COMPACT_THRESHOLD = 10


def _build_skills_context(
    skill_service: SkillService,
    kb_summary: str | None = None,
    history_summary: str | None = None,
    incident_description: str | None = None,
) -> str:
    """构建 skills 上下文，包含结构化使用规则和全量 XML 目录。

    两层格式策略:
    - Full format (≤10): <skill><name>...</name><description>...</description></skill>
    - Compact format (>10): <skill name="slug">description</skill> 单行
    """
    skill_log = get_logger(component="skill")
    available = skill_service.get_available_skills()

    if not available:
        skill_log.info("No available skills")
        return ""

    slugs = [s["slug"] for s in available]
    fmt = "compact" if len(available) > _COMPACT_THRESHOLD else "full"
    skill_log.info("_build_skills_context", count=len(available), format=fmt, slugs=slugs)

    xml_lines = [
        "\n<available_skills>",
        "使用规则:",
        '1. 通用技能优先: 若存在 `incident-triage`，默认先 `read_skill("incident-triage")` 获取分诊骨架，再切到专项技能。',
        '2. 渐进加载: 先读 SKILL.md 主体获取流程概要；scripts/references 等子文件只在执行到相关步骤时再按需加载（read_skill("slug/scripts/xxx")）。',
        "3. 上下文控制: 技能内容较长时，在推理中总结关键步骤和命令，不要大段复制粘贴原文。",
        "4. 多技能协调: 多个技能同时匹配时，选最小必要集合，声明使用顺序和原因。",
        "5. 缺失回退: 若匹配的技能无法读取或不适用当前场景，简要说明原因，用通用排查方法继续。",
    ]

    if len(available) > _COMPACT_THRESHOLD:
        for s in available:
            xml_lines.append(f'  <skill name="{s["slug"]}">{s["description"]}</skill>')
    else:
        for s in available:
            xml_lines.append(
                f"  <skill><name>{s['slug']}</name>"
                f"<description>{s['description']}</description></skill>"
            )

    xml_lines.append("</available_skills>")
    return "\n".join(xml_lines)


def get_llm():
    s = get_settings()
    return ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )


def _log_retry(retry_state):
    get_logger(component="main").warning(
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
    """Invoke LLM with retry and timeout."""
    return await asyncio.wait_for(llm.ainvoke(messages), timeout=120)


def _sanitize_llm_response(response: AIMessage, valid_tool_names: set[str]) -> AIMessage:
    """Strip invalid tool_calls when the model hallucinates an unknown tool.

    Keeps original content so the retry mechanism can handle it uniformly.
    """
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    unknown_tools = sorted(
        {
            str(tc.get("name", "")).strip()
            for tc in tool_calls
            if str(tc.get("name", "")).strip() not in valid_tool_names
        }
    )
    if not unknown_tools:
        return response

    get_logger(component="main").warning("LLM returned unknown tool(s), stripping invalid calls",
                                         tools=unknown_tools,
                                         stripped_count=len(unknown_tools),
                                         kept_count=len(tool_calls) - len(unknown_tools))
    return AIMessage(content=response.content or "")


def _build_runtime_hints(state: OpsState) -> str:
    # Procedural guidance belongs in reusable skills instead of runtime hints.
    return ""


async def main_agent_node(state: OpsState) -> dict:
    sid = state["incident_id"][:8]
    log = get_logger(component="main", sid=sid)
    tools = build_tools()
    llm = get_llm().bind_tools(tools)

    history_summary = state.get("incident_history_summary")
    if history_summary:
        history_context = (
            "## 历史事件参考\n"
            "以下是与当前事件**描述相似**的历史事件。注意：描述相似不代表根因相同，"
            "你必须对当前事件独立排查验证，不要直接套用历史事件的诊断结论或修复方案。\n\n"
            f"{history_summary}"
        )
    else:
        history_context = ""

    kb_summary = state.get("kb_summary")
    if kb_summary:
        clean_summary = kb_summary.replace("\n\n[需要补充]", "").replace("[需要补充]", "")
        kb_context = f"## 项目知识库上下文\n{clean_summary}"
        if "[需要补充]" in kb_summary:
            kb_context += (
                "\n\n注意: 知识库信息不完整，排查时注意验证，必要时用 ask_human 获取具体信息"
            )
    else:
        kb_context = ""

    skill_service = SkillService()
    skills_context = _build_skills_context(
        skill_service,
        kb_summary,
        history_summary,
        state["description"],
    )
    system_prompt = MAIN_AGENT_SYSTEM_PROMPT.format(
        description=state["description"],
        severity=state["severity"],
        incident_history_context=history_context,
        kb_context=kb_context,
        skills_context=skills_context,
        runtime_hints_context="",
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    tool_names = [t.name for t in tools]
    retry_count = state.get("tool_call_retry_count", 0)
    log.info(
        "main_agent_node invoked",
        is_retry=retry_count > 0,
        retry_count=retry_count,
        history="yes" if history_summary else "no",
        kb="yes" if kb_summary else "no",
        messages=len(messages),
        tools=tool_names,
    )
    log.debug("System prompt", chars=len(system_prompt), system_prompt=system_prompt)

    t0 = time.monotonic()
    response = await _invoke_llm_with_retry(llm, messages)
    llm_elapsed = time.monotonic() - t0
    log.info("LLM responded", elapsed=f"{llm_elapsed:.2f}s")

    content_text = response.content if hasattr(response, "content") else ""
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    log.info("LLM response", content_len=len(content_text), tool_calls=len(tool_calls))
    if content_text:
        log.info("LLM content", content=content_text)
    for tc in tool_calls:
        log.info("LLM tool_call", name=tc["name"], args=tc.get("args", {}))

    safe_response = _sanitize_llm_response(response, set(tool_names))
    if safe_response is not response:
        log.info("Sanitized LLM response: stripped invalid tool_calls",
                 original_tool_calls=len(tool_calls),
                 content_len=len(safe_response.content or ""))
    return {"messages": [safe_response]}


async def _get_service_type(service_id: str) -> str:
    """Lookup service_type for a given service_id. Returns empty string on error."""
    if not service_id:
        return ""
    try:
        from src.db.connection import get_session_factory
        from src.db.models import Service
        import uuid as _uuid

        factory = get_session_factory()
        async with factory() as session:
            svc = await session.get(Service, _uuid.UUID(service_id))
            return svc.service_type if svc else ""
    except Exception:
        return ""


async def route_decision(state: OpsState) -> str:
    sid = state["incident_id"][:8]
    log = get_logger(component="main", sid=sid)
    last_message = state["messages"][-1]
    valid_tool_names = {tool.name for tool in build_tools()}

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        content_preview = ""
        if hasattr(last_message, "content") and last_message.content:
            content_preview = last_message.content[:200]

        if state.get("ask_human_count", 0) >= 5:
            log.warning("ask_human count exceeded limit, forcing complete")
            return "complete"

        max_retries = get_settings().tool_call_max_retries
        retry_count = state.get("tool_call_retry_count", 0)
        if retry_count >= max_retries:
            log.info("route_decision: no tool_calls after retries -> ask_human (fallback)", retries=retry_count, content_preview=content_preview)
            return "ask_human"

        log.info("route_decision: no tool_calls -> retry_tool_call", attempt=f"{retry_count + 1}/{max_retries}", content_preview=content_preview)
        return "retry_tool_call"

    for tool_call in last_message.tool_calls:
        name = tool_call["name"]
        if name not in valid_tool_names:
            log.warning("route_decision: unknown tool -> ask_human", tool=name)
            return "ask_human"
        if name == "complete":
            log.info("route_decision: tool=complete -> complete")
            return "complete"
        if name == "ask_human":
            if state.get("ask_human_count", 0) >= 5:
                log.warning("ask_human count exceeded limit, forcing complete")
                return "complete"
            log.info("route_decision: tool=ask_human -> ask_human")
            return "ask_human"
        if name in ("ssh_bash", "bash"):
            cmd_type = ShellSafety.classify(
                tool_call["args"].get("command", ""),
                local=(name == "bash"),
                sudo_pre_approved=state.get("sudo_approved", False),
            )
            if cmd_type in (CommandType.WRITE, CommandType.DANGEROUS, CommandType.BLOCKED):
                log.info("route_decision: need_approval", tool=name, cmd_type=cmd_type.name)
                return "need_approval"
        if name == "service_exec":
            service_type = await _get_service_type(tool_call["args"].get("service_id", ""))
            cmd_type = ServiceSafety.classify(service_type, tool_call["args"].get("command", ""))
            if cmd_type in (CommandType.WRITE, CommandType.DANGEROUS, CommandType.BLOCKED):
                log.info("route_decision: need_approval", tool="service_exec", cmd_type=cmd_type.name)
                return "need_approval"

    log.info("route_decision: -> continue")
    return "continue"
