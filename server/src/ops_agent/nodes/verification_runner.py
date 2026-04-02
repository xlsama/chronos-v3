"""Verification Sub-Agent 生命周期管理节点 —— 创建/恢复 Verification Sub-Agent。"""

import uuid

import orjson
from langchain_core.messages import HumanMessage, ToolMessage

from src.db.connection import get_session_factory
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.nodes.agent_runner import (
    _create_and_publish_approval,
    _resume_sub_agent,
    _stream_sub_agent,
)
from src.ops_agent.state import MainState
from src.ops_agent.agents.verification_graph import compile_verification_graph
from src.services.notification_service import notify_fire_and_forget


def _extract_verification_launch_info(state: MainState) -> tuple[str, str, str]:
    """从最近的 spawn_verification tool_call 中提取 answer_md, verification_plan, tool_call_id。"""
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "spawn_verification":
                    args = tc.get("args", {})
                    return (
                        args.get("answer_md", ""),
                        args.get("verification_plan", ""),
                        tc["id"],
                    )
            break
    return "", "", ""


async def _extract_verification_report(sub_graph, config) -> dict:
    """从 Verification Sub-Agent 最终状态提取 VerificationReport。"""
    graph_state = await sub_graph.aget_state(config)
    messages = graph_state.values.get("messages", [])

    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "submit_verification":
                    args = tc.get("args", {})
                    try:
                        items = orjson.loads(args.get("items", "[]"))
                    except Exception:
                        items = []
                    return {
                        "verdict": args.get("verdict", "PARTIAL"),
                        "items": items,
                        "summary": args.get("summary", ""),
                    }
            break

    return {"verdict": "PARTIAL", "items": [], "summary": "验证未能完成"}


def _format_hypothesis_results_summary(results: list[dict]) -> str:
    """将 hypothesis_results 格式化为摘要文本。"""
    if not results:
        return "无调查发现"
    lines = []
    for r in results:
        status_map = {"confirmed": "已确认", "eliminated": "已排除", "inconclusive": "证据不足"}
        status_zh = status_map.get(r.get("status", ""), r.get("status", ""))
        lines.append(
            f"- {r.get('hypothesis_id', '?')} [{status_zh}] "
            f"{r.get('hypothesis_desc', '')}: {r.get('summary', '')}"
        )
    return "\n".join(lines)


async def run_verification_node(state: MainState) -> dict:
    """创建或恢复 Verification Sub-Agent。

    由 main_agent 调用 spawn_verification 后触发。
    完成后返回 ToolMessage + VerificationReport 给 main_agent。
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="run_verification", sid=sid)
    incident_id = state["incident_id"]

    from src.main import get_checkpointer

    checkpointer = get_checkpointer()
    sub_graph = compile_verification_graph(checkpointer=checkpointer)

    channel = EventPublisher.channel_for_incident(incident_id)
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())

    sub_thread_id = state.get("active_verification_thread_id")
    is_resume = bool(sub_thread_id)

    if not is_resume:
        answer_md, verification_plan, launch_tool_call_id = (
            _extract_verification_launch_info(state)
        )

        sub_thread_id = str(uuid.uuid4())
        log.info("Creating verification sub-agent", thread_id=sub_thread_id)

        initial_prompt = (
            f"请验证以下排查结论：\n\n{answer_md}\n\n"
            f"验证计划：\n{verification_plan}"
        )

        initial_state = {
            "messages": [HumanMessage(content=initial_prompt)],
            "incident_id": incident_id,
            "description": state["description"],
            "severity": state["severity"],
            "answer_md": answer_md,
            "hypothesis_results": list(state.get("hypothesis_results") or []),
            "kb_summary": state.get("kb_summary"),
            "is_complete": False,
            "needs_approval": False,
            "pending_tool_call": None,
            "approval_decision": None,
            "approval_supplement": None,
            "ask_human_count": 0,
            "tool_call_retry_count": 0,
        }

        config = {
            "configurable": {"thread_id": sub_thread_id},
            "recursion_limit": get_settings().agent_recursion_limit,
        }

        try:
            await publisher.publish(
                channel,
                "agent_started",
                {
                    "hypothesis_id": "VERIFY",
                    "hypothesis_title": "验证结论",
                    "hypothesis_desc": "验证排查结论和修复效果",
                    "sub_agent_thread_id": sub_thread_id,
                    "phase": "verification",
                },
            )
        except Exception as e:
            log.warning("Failed to publish agent_started", error=str(e))

        result = await _stream_sub_agent(
            sub_graph, initial_state, config, channel, publisher,
            "VERIFY", log, phase="verification",
        )
    else:
        launch_tool_call_id = state.get("pending_verify_tool_call_id", "")

        log.info("Resuming verification sub-agent", thread_id=sub_thread_id)

        config = {
            "configurable": {"thread_id": sub_thread_id},
            "recursion_limit": get_settings().agent_recursion_limit,
        }

        approval_id_for_resume = ""
        if state.get("approval_decision") == "approved" and state.get("pending_approval_id"):
            approval_id_for_resume = state["pending_approval_id"]

        result = await _resume_sub_agent(
            sub_graph, config, state, channel, publisher,
            "VERIFY", log,
            approval_id=approval_id_for_resume,
            phase="verification",
        )

    # Verification Sub-Agent hit interrupt
    if result["needs_interrupt"]:
        log.info("Verification sub-agent hit interrupt", interrupt_type=result["interrupt_type"])
        return_state: dict = {
            "active_verification_thread_id": sub_thread_id,
            "pending_verify_tool_call_id": launch_tool_call_id,
            "verification_status": "waiting_for_human",
        }
        if result["interrupt_type"] == "human_approval":
            pending = result.get("pending_tool_call")
            approval_id = await _create_and_publish_approval(
                publisher, channel, pending,
                incident_id, state["description"], state["severity"],
                "VERIFY", log, phase="verification",
            )
            return_state["needs_approval"] = True
            return_state["pending_tool_call"] = pending
            return_state["pending_approval_id"] = approval_id
        elif result["interrupt_type"] == "ask_human":
            return_state["needs_approval"] = False
            return_state["pending_tool_call"] = None
            return_state["pending_approval_id"] = None
            notify_fire_and_forget(
                "ask_human",
                incident_id,
                state.get("description", "")[:80],
                severity=state.get("severity", ""),
                question="（验证 Agent 提问）",
            )
        return return_state

    # Verification Sub-Agent 完成
    report = await _extract_verification_report(sub_graph, config)
    log.info("Verification completed", verdict=report["verdict"])

    try:
        await publisher.publish(
            channel,
            "agent_completed",
            {
                "hypothesis_id": "VERIFY",
                "status": report["verdict"].lower(),
                "summary": report["summary"][:500],
                "phase": "verification",
            },
        )
    except Exception as e:
        log.warning("Failed to publish agent_completed", error=str(e))

    verdict_zh = {"PASS": "通过", "FAIL": "失败", "PARTIAL": "部分通过"}
    tool_message_content = (
        f"验证完成。\n"
        f"判定: {verdict_zh.get(report['verdict'], report['verdict'])}\n"
        f"摘要: {report['summary']}"
    )

    return {
        "messages": [ToolMessage(content=tool_message_content, tool_call_id=launch_tool_call_id)],
        "verification_report": report,
        "active_verification_thread_id": None,
        "verification_status": "completed",
        "pending_verify_tool_call_id": None,
        "needs_approval": False,
        "pending_tool_call": None,
        "pending_approval_id": None,
    }
