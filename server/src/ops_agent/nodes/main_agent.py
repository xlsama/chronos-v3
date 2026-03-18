import asyncio

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
    async def use_skill(skill_slug: str) -> str:
        """调用预设技能获取详细排查步骤。传入技能 slug 标识符，返回完整排查指南。"""
        service = SkillService()
        try:
            meta, content = service.get_skill(skill_slug)
            return f"## 技能: {meta.name}\n\n{content}"
        except FileNotFoundError:
            return f"未找到名为 '{skill_slug}' 的技能"

    @tool
    def complete(answer_md: str) -> str:
        """排查完成后调用。answer_md 是给用户看的正式回答，要直面问题、给出结论和建议。"""
        return answer_md

    return [bash, list_servers, use_skill, ask_human, complete]


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
        kb_context = f"## 项目知识库上下文\n{kb_summary}"
    else:
        kb_context = ""

    # Build skills context
    skill_service = SkillService()
    auto_load_skills = skill_service.get_auto_load_skills()
    all_summaries = skill_service.get_all_summaries()
    auto_load_slugs = {meta.slug for meta, _ in auto_load_skills}

    lines = []
    if auto_load_skills:
        lines.append("## 预加载技能（直接使用，无需调用 use_skill）")
        for meta, content in auto_load_skills:
            lines.append(f"\n### {meta.name}\n")
            lines.append(content)

    other_summaries = [s for s in all_summaries if s["slug"] not in auto_load_slugs]
    if other_summaries:
        lines.append("\n## 其他可用技能")
        lines.append("你可以通过 use_skill 工具调用以下预设技能：\n")
        for s in other_summaries:
            lines.append(f"- `{s['slug']}` ({s['name']}): {s['description']}")

    skills_context = "\n".join(lines)

    system_prompt = MAIN_AGENT_SYSTEM_PROMPT.format(
        description=state["description"],
        severity=state["severity"],
        project_id=state.get("project_id", ""),
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
