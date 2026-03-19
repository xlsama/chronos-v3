import asyncio
import re

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.ops_agent.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import OpsState
from src.config import get_settings
from src.ops_agent.tools.bash_tool import bash as _bash, list_servers as _list_servers
from src.ops_agent.tools.safety import CommandSafety, CommandType
from src.services.skill_service import SkillService
from src.lib.logger import logger


def build_tools():
    from langchain_core.tools import tool

    @tool
    async def bash(server_id: str, command: str, explanation: str = "") -> dict:
        """在目标服务器执行 Shell 命令。
        命令通过 SSH 在 server_id 对应的远程主机上运行，不是在 agent 自身容器中运行。
        `localhost`、`127.0.0.1`、文件路径、监听端口都必须按目标服务器视角解释。
        系统自动判断命令权限：只读命令直接执行，写操作需人工审批。
        网络请求用 curl，文件操作用 cat/sed/tee 等标准命令。
        - server_id: 必须是 list_servers() 返回的有效 UUID
        - command: 要执行的 Shell 命令
        - explanation: 可选，写操作时提供操作说明（展示在审批卡片上）
        """
        return await _bash(server_id=server_id, command=command)

    @tool
    async def list_servers() -> list[dict]:
        """List all available servers. Returns id, name, host, status.
        Use this to discover target server when KB context is insufficient.
        """
        return await _list_servers()

    @tool
    def ask_human(question: str) -> str:
        """当你缺少关键信息无法继续排查时，向用户提问。
        例如：不确定事件涉及哪个服务、哪个服务器、需要额外上下文等。
        """
        return question

    @tool
    def read_skill(path: str) -> str:
        """读取技能文件。查看 <available_skills> 后，用此工具读取匹配技能。
        - "?" → 列出所有可用技能
        - "mysql-oom" → SKILL.md 内容 + 文件目录
        - "mysql-oom/scripts/check.sh" → 脚本内容
        """
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
    def complete(answer_md: str) -> str:
        """排查完成后调用。answer_md 是给用户看的正式回答，要直面问题、给出结论和建议。"""
        return answer_md

    return [bash, list_servers, read_skill, ask_human, complete]


_COMPACT_THRESHOLD = 10   # >10 个 skill 使用 compact 格式
_TRUNCATE_THRESHOLD = 30  # >30 个 skill 进行截断
_DISCOVERY_INTENT_TERMS = (
    "服务发现",
    "服务器画像",
    "摸清环境",
    "跑了什么服务",
    "跑了哪些服务",
    "这台机器跑了什么",
    "这台服务器跑了什么",
    "有哪些端口",
    "有哪些容器",
    "数据库在哪",
    "数据库在哪台",
    "数据库地址",
    "数据库服务器",
    "几张表",
    "表数量",
    "多少数据",
    "多少条数据",
    "row count",
    "table count",
    "schema",
)
_EXPLICIT_LOCATION_PATTERNS = (
    r"\b(?:postgres|postgresql|mysql|mariadb|redis)://",
    r"\b(?:db_)?host\s*[:=]\s*[a-z0-9_.:-]+",
    r"\b(?:db_)?port\s*[:=]\s*\d+",
    r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b",
    r"\blocalhost:\d+\b",
    r"\b127\.0\.0\.1(?::\d+)?\b",
    r"\b(?:postgres|postgresql|mysql|mariadb|redis)\s+server\b",
    r"\bserver_id\b",
)


def _build_skills_context(
    skill_service: SkillService,
    kb_summary: str | None = None,
    history_summary: str | None = None,
    incident_description: str | None = None,
) -> str:
    """构建 skills 上下文，包含推荐和 XML 目录。

    三层截断策略:
    - Full format (≤10): <skill><name>...</name><description>...</description></skill>
    - Compact format (10-30): <skill name="slug">description</skill> 单行
    - Truncate (>30): 只注入推荐的 + 最近使用的，其余折叠
    """
    available = skill_service.get_available_skills()

    lines: list[str] = []

    # Skill 推荐
    recommended = _recommend_skills(available, kb_summary, history_summary, incident_description)
    recommended_slugs = {s["slug"] for s in recommended}
    if recommended:
        lines.append("\n## 推荐技能")
        lines.append("基于上下文匹配，建议优先用 read_skill 读取:")
        for s in recommended:
            lines.append(f"- {s['slug']}: {s['description']}")

    # XML 目录
    if available:
        total = len(available)

        if total > _TRUNCATE_THRESHOLD:
            # 截断模式: 只显示推荐的，其余折叠
            shown = [s for s in available if s["slug"] in recommended_slugs]
            hidden_count = total - len(shown)
            xml_lines = [
                "\n<available_skills>",
                "扫描技能描述。匹配则用 read_skill 读取，按指示操作。不匹配则跳过。",
            ]
            for s in shown:
                xml_lines.append(
                    f'  <skill name="{s["slug"]}">{s["description"]}</skill>'
                )
            if hidden_count > 0:
                xml_lines.append(
                    f'  <!-- 还有 {hidden_count} 个技能，用 read_skill("?") 查看完整列表 -->'
                )
            xml_lines.append("</available_skills>")
            lines.extend(xml_lines)

        elif total > _COMPACT_THRESHOLD:
            # Compact 模式: 单行格式
            xml_lines = [
                "\n<available_skills>",
                "扫描技能描述。匹配则用 read_skill 读取，按指示操作。不匹配则跳过。",
            ]
            for s in available:
                xml_lines.append(
                    f'  <skill name="{s["slug"]}">{s["description"]}</skill>'
                )
            xml_lines.append("</available_skills>")
            lines.extend(xml_lines)

        else:
            # Full 模式
            xml_lines = [
                "\n<available_skills>",
                "扫描技能描述。匹配则用 read_skill 读取，按指示操作。不匹配则跳过。",
            ]
            for s in available:
                xml_lines.append(
                    f'  <skill><name>{s["slug"]}</name>'
                    f'<description>{s["description"]}</description></skill>'
                )
            xml_lines.append("</available_skills>")
            lines.extend(xml_lines)

    return "\n".join(lines)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _has_explicit_target_location(*contexts: str | None) -> bool:
    for context in contexts:
        if not context:
            continue
        lowered = context.lower()
        if any(re.search(pattern, lowered) for pattern in _EXPLICIT_LOCATION_PATTERNS):
            return True
    return False


def _tokenize_skill_keywords(skill: dict) -> set[str]:
    keywords: set[str] = set()
    for field in (skill["slug"], skill.get("name", ""), skill.get("description", "")):
        lowered = field.lower()
        keywords.update(
            token
            for token in re.split(r"[^a-z0-9]+", lowered)
            if len(token) > 2
        )
    return keywords


def _recommend_skills(
    available: list[dict],
    kb_summary: str | None,
    history_summary: str | None,
    incident_description: str | None = None,
) -> list[dict]:
    """基于 incident/kb/history 上下文关键词匹配推荐技能。"""
    if not available:
        return []

    contexts = [incident_description, kb_summary, history_summary]
    context = " ".join(part.lower() for part in contexts if part)

    if not context.strip():
        return []

    recommended_scored: list[tuple[int, dict]] = []
    has_explicit_location = _has_explicit_target_location(kb_summary, history_summary)
    has_discovery_intent = _contains_any(context, _DISCOVERY_INTENT_TERMS)

    for skill in available:
        score = 0

        # 服务发现对“先确认服务/数据库部署位置”的问题做定向推荐。
        if skill["slug"] == "service-discovery":
            if has_discovery_intent and not has_explicit_location:
                score += 3

        keywords = _tokenize_skill_keywords(skill)
        score += sum(1 for kw in keywords if kw in context)

        if score > 0:
            recommended_scored.append((score, skill))

    recommended_scored.sort(key=lambda item: item[0], reverse=True)
    return [skill for _, skill in recommended_scored[:3]]


def get_llm():
    s = get_settings()
    return ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
    before_sleep=lambda retry_state: logger.warning(
        f"LLM call failed (attempt {retry_state.attempt_number}), retrying: {retry_state.outcome.exception()}"
    ),
)
async def _invoke_llm_with_retry(llm, messages):
    """Invoke LLM with retry and timeout."""
    return await asyncio.wait_for(llm.ainvoke(messages), timeout=120)


async def main_agent_node(state: OpsState) -> dict:
    sid = state["incident_id"][:8]
    tools = build_tools()
    llm = get_llm().bind_tools(tools)

    history_summary = state.get("incident_history_summary")
    if history_summary:
        history_context = f"## 历史事件参考\n以下是与当前事件相似的历史事件供参考：\n\n{history_summary}"
    else:
        history_context = ""

    kb_summary = state.get("kb_summary")
    if kb_summary:
        clean_summary = kb_summary.replace("\n\n[需要补充]", "").replace("[需要补充]", "")
        kb_context = f"## 项目知识库上下文\n{clean_summary}"
        if "[需要补充]" in kb_summary:
            kb_context += "\n\n注意: 知识库信息不完整，排查时注意验证，必要时用 ask_human 获取具体信息"
    else:
        kb_context = ""

    # Build skills context
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
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    logger.info(f"[{sid}] [main] main_agent_node invoked, history={'yes' if history_summary else 'no'}, kb={'yes' if kb_summary else 'no'}")

    response = await _invoke_llm_with_retry(llm, messages)

    content_text = response.content if hasattr(response, "content") else ""
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    logger.info(f"\n[{sid}] [main] LLM response: content_len={len(content_text)}, tool_calls={len(tool_calls)}")
    if content_text:
        logger.info(f"\n[{sid}] [main] LLM content:\n{content_text}\n")
    for tc in tool_calls:
        logger.info(f"\n[{sid}] [main] LLM tool_call: {tc['name']}({tc.get('args', {})})")

    return {"messages": [response]}


def route_decision(state: OpsState) -> str:
    sid = state["incident_id"][:8]
    last_message = state["messages"][-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        # Check ask_human count to prevent infinite loops
        if state.get("ask_human_count", 0) >= 5:
            logger.warning(f"[{sid}] [main] ask_human count exceeded limit, forcing complete")
            return "complete"
        logger.info(f"[{sid}] [main] route_decision: no tool_calls -> ask_human")
        return "ask_human"

    for tool_call in last_message.tool_calls:
        name = tool_call["name"]
        if name == "complete":
            logger.info(f"[{sid}] [main] route_decision: tool=complete -> complete")
            return "complete"
        if name == "ask_human":
            # Check ask_human count
            if state.get("ask_human_count", 0) >= 5:
                logger.warning(f"[{sid}] [main] ask_human count exceeded limit, forcing complete")
                return "complete"
            logger.info(f"[{sid}] [main] route_decision: tool=ask_human -> ask_human")
            return "ask_human"
        if name == "bash":
            cmd_type = CommandSafety.classify(tool_call["args"].get("command", ""))
            if cmd_type in (CommandType.WRITE, CommandType.DANGEROUS, CommandType.BLOCKED):
                logger.info(f"[{sid}] [main] route_decision: need_approval (cmd_type={cmd_type.name})")
                return "need_approval"

    logger.info(f"[{sid}] [main] route_decision: -> continue")
    return "continue"
