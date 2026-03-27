"""协调者 LLM 节点 —— 调度子 Agent、评估结果、更新计划、输出结论。"""

import time
import uuid
from typing import Annotated

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import InjectedState
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.db.connection import get_session_factory
from src.db.models import Incident
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.prompts.coordinator_agent import COORDINATOR_AGENT_SYSTEM_PROMPT
from src.ops_agent.state import CoordinatorState


def build_coordinator_tools():
    """构建协调者的工具集。"""
    from langchain_core.tools import tool

    @tool
    def launch_investigation(
        hypothesis_id: str, hypothesis_title: str, hypothesis_desc: str
    ) -> str:
        """启动一个子 Agent 来验证指定假设。
        子 Agent 会独立执行排查（SSH 命令、数据库查询等），完成后返回调查结果。
        - hypothesis_id: 假设编号，如 "H1"
        - hypothesis_title: 假设短标题（15字以内，如"数据库连接池耗尽"、"查询条件过滤异常"）
        - hypothesis_desc: 假设详细描述（含具体排查方向和步骤）
        """
        return f"子 Agent 已启动，正在验证假设 {hypothesis_id}: {hypothesis_title}"

    @tool
    async def update_plan(
        plan_md: str,
        state: Annotated[dict, InjectedState],
    ) -> str:
        """更新调查计划。收到子 Agent 结果后，更新假设状态和证据。
        输入完整的更新后调查计划（Markdown 格式），会替换当前计划。
        将假设状态从 [待验证]/[排查中] 更新为 [已确认] 或 [已排除]。
        - plan_md: 更新后的完整调查计划 Markdown
        """
        incident_id = state["incident_id"]
        log = get_logger(component="update_plan")
        try:
            async with get_session_factory()() as session:
                incident = await session.get(Incident, uuid.UUID(incident_id))
                if incident:
                    incident.plan_md = plan_md
                    await session.commit()
        except Exception as e:
            log.warning("Failed to save plan to DB", error=str(e))
        try:
            channel = EventPublisher.channel_for_incident(incident_id)
            publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
            await publisher.publish(
                channel, "plan_updated", {"plan_md": plan_md, "phase": "investigation"}
            )
        except Exception as e:
            log.warning("Failed to publish plan_updated event", error=str(e))
        return "调查计划已更新"

    @tool
    def complete(answer_md: str) -> str:
        """排查完成，输出最终结论。answer_md 是完整的排查报告（Markdown），包含根因、证据链、建议。
        只在所有排查完成、问题已解决或已充分诊断后调用。
        - answer_md: 排查结论的 Markdown 内容
        """
        return answer_md

    return [launch_investigation, update_plan, complete]


def _get_coordinator_llm():
    s = get_settings()
    return ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )


def _log_retry(retry_state):
    get_logger(component="coordinator").warning(
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
    """Strip invalid tool_calls."""
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    unknown = [tc for tc in tool_calls if str(tc.get("name", "")).strip() not in valid_tool_names]
    if not unknown:
        return response
    get_logger(component="coordinator").warning(
        "Stripping unknown tool calls", tools=[tc.get("name") for tc in unknown]
    )
    return AIMessage(content=response.content or "")


async def _build_plan_context(incident_id: str) -> str:
    """从 DB 读取调查计划。"""
    try:
        async with get_session_factory()() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if incident and incident.plan_md:
                return f"## 当前调查计划\n\n{incident.plan_md}"
    except Exception:
        pass
    return ""


async def coordinator_agent_node(state: CoordinatorState) -> dict:
    """协调者 LLM 节点。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="coordinator", sid=sid)

    tools = build_coordinator_tools()
    llm = _get_coordinator_llm().bind_tools(tools)

    # 构建上下文
    history_summary = state.get("incident_history_summary")
    history_context = ""
    if history_summary:
        history_context = (
            "## 历史事件参考\n"
            "以下是与当前事件描述相似的历史事件（仅供参考，不代表当前根因相同）：\n\n"
            f"{history_summary}"
        )

    kb_summary = state.get("kb_summary")
    kb_context = f"## 项目知识库上下文\n{kb_summary}" if kb_summary else ""

    plan_context = await _build_plan_context(state["incident_id"])

    system_prompt = COORDINATOR_AGENT_SYSTEM_PROMPT.format(
        description=state["description"],
        severity=state["severity"],
        incident_history_context=history_context,
        kb_context=kb_context,
        plan_context=plan_context,
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    tool_names = [t.name for t in tools]
    log.info(
        "coordinator_agent_node invoked",
        messages=len(messages),
        tools=tool_names,
    )

    t0 = time.monotonic()
    response = await _invoke_llm_with_retry(llm, messages)
    elapsed = time.monotonic() - t0
    log.info("LLM responded", elapsed=f"{elapsed:.2f}s")

    content_text = response.content if hasattr(response, "content") else ""
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    log.info("LLM response", content_len=len(content_text), tool_calls=len(tool_calls))
    if content_text:
        log.info("LLM content", content=content_text)
    for tc in tool_calls:
        log.info("LLM tool_call", name=tc["name"], args=tc.get("args", {}))

    safe_response = _sanitize_llm_response(response, set(tool_names))

    # 如果 LLM 调用了 launch_investigation，保存 tool_call_id 用于 ToolMessage 回复
    result: dict = {"messages": [safe_response]}
    if hasattr(safe_response, "tool_calls") and safe_response.tool_calls:
        for tc in safe_response.tool_calls:
            if tc["name"] == "launch_investigation":
                result["pending_launch_tool_call_id"] = tc["id"]
                break

    return result


async def route_coordinator_decision(state: CoordinatorState) -> str:
    """路由协调者的下一步。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="coordinator", sid=sid)
    last_message = state["messages"][-1]
    tools = build_coordinator_tools()
    valid_tool_names = {t.name for t in tools}

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        max_retries = get_settings().tool_call_max_retries
        retry_count = state.get("tool_call_retry_count", 0)
        if retry_count >= max_retries:
            log.info("no tool_calls after retries -> force complete")
            return "complete"
        log.info("no tool_calls -> retry_tool_call")
        return "retry_tool_call"

    for tc in last_message.tool_calls:
        name = tc["name"]
        if name not in valid_tool_names:
            log.warning("unknown tool -> retry", tool=name)
            return "retry_tool_call"
        if name == "launch_investigation":
            log.info("-> run_sub_agent", hypothesis=tc["args"].get("hypothesis_id"))
            return "launch_investigation"
        if name == "complete":
            log.info("-> confirm_resolution")
            return "complete"

    # update_plan 等其他工具 → coordinator_tools (ToolNode)
    log.info("-> coordinator_tools (continue)")
    return "continue"
