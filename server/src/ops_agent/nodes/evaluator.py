import asyncio
import json
import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from src.db.connection import get_session_factory
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.prompts.evaluator import EVALUATOR_SYSTEM_PROMPT, EVALUATOR_USER_PROMPT
from src.ops_agent.state import OpsState
from src.ops_agent.tools.ssh_bash_tool import ssh_bash as _ssh_bash, list_servers as _list_servers
from src.ops_agent.tools.bash_tool import local_bash as _local_bash
from src.ops_agent.tools.service_exec_tool import (
    service_exec as _service_exec,
    list_services as _list_services,
)

MAX_EVAL_TOOL_CALLS = 5
MAX_EVAL_ATTEMPTS = 2


def _build_eval_tools():
    """构建评估器的只读工具集。"""
    from langchain_core.tools import tool

    @tool
    async def ssh_bash(server_id: str, command: str) -> dict:
        """在目标服务器执行只读 Shell 命令（通过 SSH）。"""
        return await _ssh_bash(server_id=server_id, command=command)

    @tool
    async def bash(command: str) -> dict:
        """在本地执行只读命令。"""
        return await _local_bash(command=command)

    @tool
    async def service_exec(service_id: str, command: str) -> str:
        """直连服务执行只读查询。"""
        return await _service_exec(service_id=service_id, command=command)

    @tool
    async def list_servers() -> list[dict] | str:
        """列出所有可用服务器。"""
        result = await _list_servers()
        if not result:
            return "当前没有注册任何服务器。"
        return result

    @tool
    async def list_services() -> list[dict] | str:
        """列出所有可用服务。"""
        result = await _list_services()
        if not result:
            return "当前没有注册任何服务。"
        return result

    return [ssh_bash, bash, service_exec, list_servers, list_services]


def _parse_evaluation_result(text: str) -> dict | None:
    """从 LLM 响应中提取评估结果 JSON。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            if line.strip() == "```" and in_block:
                break
            if in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    try:
        result = json.loads(text)
        # 验证必需字段
        required = {"outcome_type", "verification_passed", "confidence", "recommendation"}
        if required.issubset(result.keys()):
            return result
        return None
    except json.JSONDecodeError:
        return None


async def _run_evaluator(state: OpsState) -> dict:
    """运行评估器的 LLM + tool 调用循环。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="evaluator", sid=sid)

    s = get_settings()
    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
    )

    tools = _build_eval_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    # 从 main_agent 的最后一个 complete() 调用中提取 answer_md
    answer_md = ""
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == "complete":
                    answer_md = tc.get("args", {}).get("answer_md", "")
                    break
            if answer_md:
                break

    plan = state.get("investigation_plan")
    plan_str = json.dumps(plan, ensure_ascii=False, indent=2) if plan else "无调查计划"

    user_prompt = EVALUATOR_USER_PROMPT.format(
        description=state["description"],
        answer_md=answer_md,
        investigation_plan=plan_str,
    )

    messages = [
        SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    tool_call_count = 0
    for i in range(MAX_EVAL_TOOL_CALLS + 1):
        t0 = time.monotonic()
        response = await asyncio.wait_for(llm_with_tools.ainvoke(messages), timeout=60)
        elapsed = time.monotonic() - t0

        content = response.content if hasattr(response, "content") else ""
        tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []

        log.info(
            "evaluator LLM response",
            iteration=i + 1,
            elapsed=f"{elapsed:.2f}s",
            content_len=len(content),
            tool_calls=len(tool_calls),
        )

        if not tool_calls:
            # 尝试从 content 中解析 JSON 结果
            result = _parse_evaluation_result(content)
            if result:
                return result
            # LLM 没有返回有效的 JSON，构造默认结果
            log.warning("Evaluator returned no valid JSON", content=content[:500])
            return {
                "outcome_type": "insufficient_evidence",
                "verification_passed": False,
                "confidence": "low",
                "evidence_summary": content[:500] if content else "评估器未能产出结构化结果",
                "concerns": ["评估器未能完成验证"],
                "recommendation": "confirm_with_user",
            }

        messages.append(response)

        # 执行 tool calls
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("args", {})

            if name not in tool_map:
                messages.append(
                    ToolMessage(
                        content=f"未知工具: {name}",
                        tool_call_id=tc["id"],
                    )
                )
                continue

            tool_call_count += 1
            log.info("evaluator tool_call", name=name, args=args, count=tool_call_count)

            try:
                result = await tool_map[name].ainvoke(args)
                result_str = str(result)
                if len(result_str) > 5000:
                    result_str = result_str[:5000] + "\n... (已截断)"
            except Exception as e:
                result_str = f"工具执行失败: {e}"
                log.warning("evaluator tool error", name=name, error=str(e))

            messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

        if tool_call_count >= MAX_EVAL_TOOL_CALLS:
            log.info("evaluator reached max tool calls, requesting final response")
            messages.append(
                HumanMessage(
                    content="你已达到最大工具调用次数。请根据已有证据输出最终的 JSON 评估结果。"
                )
            )

    # 最终兜底
    return {
        "outcome_type": "insufficient_evidence",
        "verification_passed": False,
        "confidence": "low",
        "evidence_summary": "评估器达到迭代上限",
        "concerns": ["未能完成完整验证"],
        "recommendation": "confirm_with_user",
    }


async def evaluator_node(state: OpsState) -> dict:
    """评估 Agent 的结论是否正确。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="evaluator", sid=sid)

    attempts = state.get("evaluation_attempts", 0)
    log.info("===== Evaluator started =====", attempt=attempts + 1)

    # 发布 evaluation_started 事件
    try:
        channel = EventPublisher.channel_for_incident(state["incident_id"])
        publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
        await publisher.publish(
            channel,
            "evaluation_started",
            {
                "attempt": attempts + 1,
                "phase": "evaluation",
            },
        )
    except Exception as e:
        log.warning("Failed to publish evaluation_started event", error=str(e))

    t0 = time.monotonic()
    try:
        result = await _run_evaluator(state)
    except Exception as e:
        log.error("Evaluator failed", error=str(e))
        result = {
            "outcome_type": "insufficient_evidence",
            "verification_passed": False,
            "confidence": "low",
            "evidence_summary": f"评估器执行异常: {e}",
            "concerns": ["评估器执行失败"],
            "recommendation": "confirm_with_user",
        }
    elapsed = time.monotonic() - t0

    log.info(
        "===== Evaluator completed =====",
        elapsed=f"{elapsed:.2f}s",
        outcome_type=result.get("outcome_type"),
        verification_passed=result.get("verification_passed"),
        recommendation=result.get("recommendation"),
    )

    # 发布 evaluation_completed 事件
    try:
        channel = EventPublisher.channel_for_incident(state["incident_id"])
        publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
        await publisher.publish(
            channel,
            "evaluation_completed",
            {
                "result": result,
                "phase": "evaluation",
            },
        )
    except Exception as e:
        log.warning("Failed to publish evaluation_completed event", error=str(e))

    return {
        "evaluation_result": result,
        "evaluation_attempts": attempts + 1,
    }


def route_after_evaluation(state: OpsState) -> str:
    """评估后的路由：验证通过去确认，否则打回给 Agent。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="evaluator", sid=sid)

    attempts = state.get("evaluation_attempts", 0)
    result = state.get("evaluation_result", {})
    recommendation = result.get("recommendation", "confirm_with_user")

    # 超过最大尝试次数，强制交给用户
    if attempts >= MAX_EVAL_ATTEMPTS:
        log.info(
            "route_after_evaluation: max attempts reached -> confirm_resolution", attempts=attempts
        )
        return "confirm_resolution"

    if recommendation == "return_to_agent":
        log.info(
            "route_after_evaluation: -> main_agent", reason=result.get("evidence_summary", "")[:200]
        )
        return "main_agent"

    log.info("route_after_evaluation: -> confirm_resolution")
    return "confirm_resolution"
