from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from src.ops_agent.prompts.main_agent import MAIN_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import OpsState
from src.config import get_settings
from src.ops_agent.tools.bash_tool import bash as _bash, list_servers as _list_servers
from src.ops_agent.tools.safety import CommandSafety, CommandType
from src.services.skill_service import SkillService


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
    async def list_servers(project_id: str = "") -> list[dict]:
        """List available servers. Returns id, name, host, status.
        Use this to discover target server when KB context is insufficient.
        Optionally pass project_id to filter by project.
        """
        return await _list_servers(project_id=project_id)

    @tool
    def ask_human(question: str) -> str:
        """当你缺少关键信息无法继续排查时，向用户提问。
        例如：不确定事件涉及哪个服务、哪个服务器、需要额外上下文等。
        """
        return question

    @tool
    async def use_skill(skill_name: str) -> str:
        """调用预设技能获取详细排查步骤。传入技能名称，返回完整排查指南。"""
        service = SkillService()
        try:
            meta, content = service.get_skill_by_name(skill_name)
            return f"## 技能: {meta.name}\n\n{content}"
        except FileNotFoundError:
            return f"未找到名为 '{skill_name}' 的技能"

    @tool
    def complete(summary: str) -> str:
        """Call this when the investigation is complete. Provide a brief summary."""
        return summary

    return [bash, list_servers, use_skill, ask_human, complete]


def get_llm():
    s = get_settings()
    return ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )


async def main_agent_node(state: OpsState) -> dict:
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
    skill_summaries = SkillService().get_all_summaries()
    if skill_summaries:
        lines = ["## 可用技能", "你可以通过 use_skill 工具调用以下预设技能：", ""]
        for s in skill_summaries:
            lines.append(f"- **{s['name']}**: {s['description']}")
        skills_context = "\n".join(lines)
    else:
        skills_context = ""

    system_prompt = MAIN_AGENT_SYSTEM_PROMPT.format(
        description=state["description"],
        severity=state["severity"],
        project_id=state.get("project_id", ""),
        incident_history_context=history_context,
        kb_context=kb_context,
        skills_context=skills_context,
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    response = await llm.ainvoke(messages)

    return {"messages": [response]}


def route_decision(state: OpsState) -> str:
    last_message = state["messages"][-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return "ask_human"

    for tool_call in last_message.tool_calls:
        name = tool_call["name"]
        if name == "complete":
            return "complete"
        if name == "ask_human":
            return "ask_human"
        if name == "bash":
            cmd_type = CommandSafety.classify(tool_call["args"].get("command", ""))
            if cmd_type in (CommandType.WRITE, CommandType.DANGEROUS, CommandType.BLOCKED):
                return "need_approval"

    return "continue"
