import asyncio
import json
import re
import time
import uuid
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from src.db.connection import get_session_factory
from src.db.models import Incident
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


async def _read_plan_from_db(incident_id: str) -> str:
    """从数据库读取调查计划 Markdown。"""
    try:
        async with get_session_factory()() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if incident and incident.plan_md:
                return incident.plan_md
    except Exception:
        pass
    return ""


def _apply_hypothesis_updates_md(plan_md: str, updates: list[dict]) -> str | None:
    """根据 hypothesis_updates 更新 Markdown 计划中的假设状态。"""
    if not plan_md or not updates:
        return None

    updated = plan_md
    changed = False
    for u in updates:
        if not isinstance(u, dict) or "id" not in u or "status" not in u:
            continue
        h_id = u["id"]
        new_status = u["status"]
        if new_status not in ("已确认", "已排除", "排查中"):
            continue
        # 替换假设标题中的状态: ### H1 [待验证] → ### H1 [已确认]
        pattern = rf"(### {re.escape(h_id)} )\[(待验证|排查中|已确认|已排除|pending|investigating|confirmed|eliminated)\]"
        replacement = rf"\1[{new_status}]"
        new_text = re.sub(pattern, replacement, updated)
        if new_text != updated:
            updated = new_text
            changed = True
        # 追加评估证据
        evidence = u.get("evidence", "")
        if evidence:
            evidence_label = "正向证据" if new_status == "已确认" else "反向证据"
            # 找到对应假设的证据行并追加
            pattern_ev = (
                rf"(### {re.escape(h_id)} \[{re.escape(new_status)}\].*?"
                rf"- \*\*{evidence_label}\*\*: )(.*?)(\n|$)"
            )
            match = re.search(pattern_ev, updated, re.DOTALL)
            if match:
                current_evidence = match.group(2).strip()
                if current_evidence == "（暂无）":
                    new_evidence = f"[评估验证] {evidence}"
                else:
                    new_evidence = f"{current_evidence}; [评估验证] {evidence}"
                updated = updated[: match.start(2)] + new_evidence + updated[match.end(2) :]

    return updated if changed else None


async def _run_evaluator(state: OpsState) -> dict:
    """运行评估器的 LLM + tool 调用循环。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="evaluator", sid=sid)

    s = get_settings()
    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )

    tools = _build_eval_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    # 从 DB 读取调查计划（包含 confirmed 假设）
    plan_md = await _read_plan_from_db(state["incident_id"])

    user_prompt = EVALUATOR_USER_PROMPT.format(
        description=state["description"],
        investigation_plan=plan_md or "无调查计划",
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
            result = _parse_evaluation_result(content)
            if result:
                return result
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

        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("args", {})

            if name not in tool_map:
                messages.append(ToolMessage(content=f"未知工具: {name}", tool_call_id=tc["id"]))
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
            {"attempt": attempts + 1, "phase": "evaluation"},
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
            {"result": result, "phase": "evaluation"},
        )
    except Exception as e:
        log.warning("Failed to publish evaluation_completed event", error=str(e))

    # 根据评估结果更新调查计划中的假设状态（Markdown 格式）
    hypothesis_updates = result.get("hypothesis_updates")
    if hypothesis_updates:
        plan_md = await _read_plan_from_db(state["incident_id"])
        if plan_md:
            updated_md = _apply_hypothesis_updates_md(plan_md, hypothesis_updates)
            if updated_md:
                # 写入 DB
                try:
                    async with get_session_factory()() as session:
                        incident = await session.get(Incident, uuid.UUID(state["incident_id"]))
                        if incident:
                            incident.plan_md = updated_md
                            await session.commit()
                except Exception as e:
                    log.warning("Failed to update plan in DB", error=str(e))
                # 发布 plan_updated 事件
                try:
                    channel = EventPublisher.channel_for_incident(state["incident_id"])
                    publisher = EventPublisher(
                        redis=get_redis(), session_factory=get_session_factory()
                    )
                    await publisher.publish(
                        channel,
                        "plan_updated",
                        {"plan_md": updated_md, "phase": "evaluation"},
                    )
                except Exception as e:
                    log.warning("Failed to publish plan_updated after evaluation", error=str(e))
                log.info(
                    "Plan updated after evaluation",
                    updates=[u.get("id") for u in hypothesis_updates],
                )

    # 验证失败打回时，回退 [已确认] → [排查中]，防止重复触发 evaluator
    if result.get("recommendation") == "return_to_agent":
        plan_md = await _read_plan_from_db(state["incident_id"])
        if plan_md:
            reverted_md = re.sub(
                r"(### H\d+) \[(已确认|confirmed)\]",
                r"\1 [排查中]",
                plan_md,
            )
            if reverted_md != plan_md:
                log.info("Reverting confirmed hypotheses to investigating after eval failure")
                try:
                    async with get_session_factory()() as session:
                        incident = await session.get(Incident, uuid.UUID(state["incident_id"]))
                        if incident:
                            incident.plan_md = reverted_md
                            await session.commit()
                except Exception as e:
                    log.warning("Failed to revert plan in DB", error=str(e))
                try:
                    channel = EventPublisher.channel_for_incident(state["incident_id"])
                    publisher = EventPublisher(
                        redis=get_redis(), session_factory=get_session_factory()
                    )
                    await publisher.publish(
                        channel,
                        "plan_updated",
                        {"plan_md": reverted_md, "phase": "evaluation"},
                    )
                except Exception as e:
                    log.warning("Failed to publish reverted plan", error=str(e))

    return {
        "evaluation_result": result,
        "evaluation_attempts": attempts + 1,
    }


def route_after_evaluation(state: OpsState) -> str:
    """评估后的路由：验证通过去生成总结，否则打回给 Agent。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="evaluator", sid=sid)

    attempts = state.get("evaluation_attempts", 0)
    result = state.get("evaluation_result", {})
    recommendation = result.get("recommendation", "confirm_with_user")

    if attempts >= MAX_EVAL_ATTEMPTS:
        log.info(
            "route_after_evaluation: max attempts reached -> generate_summary",
            attempts=attempts,
        )
        return "generate_summary"

    if recommendation == "return_to_agent":
        log.info(
            "route_after_evaluation: -> main_agent",
            reason=result.get("evidence_summary", "")[:200],
        )
        return "main_agent"

    log.info("route_after_evaluation: -> generate_summary")
    return "generate_summary"
