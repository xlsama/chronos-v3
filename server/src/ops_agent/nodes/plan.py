"""Plan 节点 —— 带只读工具的 mini agent loop，生成调查计划。

Plan Agent 可以使用 list_servers/list_services/read_skill 探查基础设施，
然后生成基于真实环境的假设。最多 3 轮工具调用，之后必须输出计划。
"""

import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.db.connection import get_session_factory
from src.db.models import Incident
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.prompts.plan import PLAN_SYSTEM_PROMPT, PLAN_USER_PROMPT
from src.ops_agent.state import MainState
from src.ops_agent.tools.registry import build_tools_for_agent

MAX_TOOL_ROUNDS = 3


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(
        (
            TimeoutError,
            ConnectionError,
            OSError,
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
        )
    ),
    before_sleep=lambda rs: get_logger(component="plan").warning(
        "Plan LLM call failed, retrying",
        attempt=rs.attempt_number,
        error=str(rs.outcome.exception()),
    ),
)
async def _invoke_llm(llm, messages):
    return await llm.ainvoke(messages)


async def _stream_plan_content(llm_no_tools, messages, publisher, channel, log):
    """最终生成计划时使用 streaming，推送 thinking 事件到前端。"""
    content = ""
    first_token_time = None
    t0 = time.monotonic()
    async for chunk in llm_no_tools.astream(messages):
        text = chunk.content if hasattr(chunk, "content") else ""
        if text:
            content += text
            if first_token_time is None:
                first_token_time = time.monotonic()
                ttft = first_token_time - t0
                log.info("First token received", ttft=f"{ttft:.2f}s")
                try:
                    await publisher.publish(
                        channel,
                        "plan_progress",
                        {
                            "status": "first_token_received",
                            "ttft": round(ttft, 2),
                            "phase": "planning",
                        },
                    )
                except Exception:
                    pass
            try:
                await publisher.publish(channel, "thinking", {"content": text, "phase": "planning"})
            except Exception:
                pass
    return content


async def _execute_tool_calls(
    tool_calls: list[dict], tools_by_name: dict, log
) -> list[ToolMessage]:
    """Execute tool calls and return ToolMessage results."""
    results = []
    for tc in tool_calls:
        name = tc["name"]
        args = tc.get("args", {})
        tool_call_id = tc["id"]
        tool_fn = tools_by_name.get(name)
        if tool_fn is None:
            results.append(ToolMessage(content=f"未知工具: {name}", tool_call_id=tool_call_id))
            continue
        try:
            if hasattr(tool_fn, "ainvoke"):
                output = await tool_fn.ainvoke(args)
            else:
                output = tool_fn.invoke(args)
            results.append(ToolMessage(content=str(output), tool_call_id=tool_call_id))
            log.info("Plan tool executed", tool=name, output_len=len(str(output)))
        except Exception as e:
            results.append(ToolMessage(content=f"工具执行失败: {e}", tool_call_id=tool_call_id))
            log.warning("Plan tool failed", tool=name, error=str(e))
    return results


async def plan_node(state: MainState) -> dict:
    """生成初始调查计划（Markdown 格式），支持只读工具探查基础设施。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="plan", sid=sid)
    log.info("===== Plan started =====")

    s = get_settings()

    # 带工具的 LLM（用于探查阶段）
    plan_tools = build_tools_for_agent("plan")
    tools_by_name = {t.name: t for t in plan_tools}
    llm_with_tools = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=False,
        extra_body={"enable_thinking": False},
    ).bind_tools(plan_tools)

    # 不带工具的 LLM（用于最终输出计划）
    llm_no_tools = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
        extra_body={"enable_thinking": False},
    )

    channel = EventPublisher.channel_for_incident(state["incident_id"])
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
    try:
        await publisher.publish(channel, "plan_started", {"phase": "planning"})
    except Exception as e:
        log.warning("Failed to publish plan_started event", error=str(e))

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
    kb_context = ""
    if kb_summary:
        kb_context = f"## 项目知识库上下文\n{kb_summary}"

    user_prompt = PLAN_USER_PROMPT.format(
        description=state["description"],
        severity=state["severity"],
        history_context=history_context,
        kb_context=kb_context,
    )

    # Plan agent system prompt 增加工具说明
    plan_system = (
        PLAN_SYSTEM_PROMPT + "\n\n## 可用工具\n"
        "- **list_servers**: 查看所有可用服务器（id, name, host, status）\n"
        "- **list_services**: 查看所有可用服务（id, name, type, host, port, status）\n"
        '- **read_skill**: 读取技能文件（"?" 列出可用技能）\n\n'
        "你可以先调用这些工具了解基础设施，再生成更准确的假设。\n"
        "也可以直接生成计划（不调用工具）。最多调用 3 轮工具。"
    )

    messages: list = [
        SystemMessage(content=plan_system),
        HumanMessage(content=user_prompt),
    ]

    # Mini agent loop: 最多 MAX_TOOL_ROUNDS 轮工具调用
    content = ""
    for round_idx in range(MAX_TOOL_ROUNDS):
        log.info("Plan agent round", round=round_idx + 1)
        response = await _invoke_llm(llm_with_tools, messages)

        tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
        response_content = response.content if hasattr(response, "content") else ""

        if not tool_calls:
            # 没有工具调用，说明 LLM 直接输出了计划内容
            content = response_content
            log.info("Plan agent produced plan without tools", round=round_idx + 1)
            break

        # 有工具调用：执行工具，把结果追加到消息中
        messages.append(response)
        tool_results = await _execute_tool_calls(tool_calls, tools_by_name, log)
        messages.extend(tool_results)

    if not content:
        # 工具轮次用完或未产生内容，用无工具 LLM streaming 生成最终计划
        log.info("Generating final plan via streaming")
        # 追加提示让 LLM 生成计划
        messages.append(
            HumanMessage(
                content="请根据上述信息生成调查计划（纯 Markdown，不要 code block 包裹）。"
            )
        )
        try:
            await publisher.publish(
                channel, "plan_progress", {"status": "llm_call_started", "phase": "planning"}
            )
        except Exception:
            pass
        content = await _stream_plan_content(llm_no_tools, messages, publisher, channel, log)
    else:
        # 直接输出的内容也需要推送 thinking 事件
        try:
            await publisher.publish(channel, "thinking", {"content": content, "phase": "planning"})
        except Exception:
            pass

    try:
        await publisher.publish(channel, "thinking_done", {"phase": "planning"})
    except Exception:
        pass

    # 清理可能的 code block 包裹
    plan_md = content.strip()
    if plan_md.startswith("```"):
        lines = plan_md.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        plan_md = "\n".join(lines).strip()

    log.info("===== Plan completed =====", plan_chars=len(plan_md))
    log.debug("investigation_plan_md", plan_md=plan_md)

    # 写入数据库
    try:
        async with get_session_factory()() as session:
            incident = await session.get(Incident, uuid.UUID(state["incident_id"]))
            if incident:
                incident.plan_md = plan_md
                await session.commit()
    except Exception as e:
        log.warning("Failed to save plan to DB", error=str(e))

    # 发布 plan_generated 事件
    try:
        await publisher.publish(
            channel,
            "plan_generated",
            {"plan_md": plan_md, "phase": "planning"},
        )
    except Exception as e:
        log.warning("Failed to publish plan_generated event", error=str(e))

    return {}
