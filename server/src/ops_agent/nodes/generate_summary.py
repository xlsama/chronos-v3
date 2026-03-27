import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.db.connection import get_session_factory
from src.db.models import Incident
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.prompts.generate_summary import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT
from src.ops_agent.state import CoordinatorState


async def generate_summary_node(state: CoordinatorState) -> dict:
    """评估通过后，流式生成排查总结报告。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="generate_summary", sid=sid)
    log.info("===== Generate summary started =====")

    # 1. 构建 prompt 上下文
    evaluation_result = state.get("evaluation_result", {})
    eval_passed = evaluation_result.get("verification_passed", False)

    evaluation_summary = ""
    if evaluation_result:
        evaluation_summary = (
            f"- 验证结果: {'通过' if eval_passed else '未通过'}\n"
            f"- 置信度: {evaluation_result.get('confidence', '未知')}\n"
            f"- 证据摘要: {evaluation_result.get('evidence_summary', '无')}\n"
        )
        concerns = evaluation_result.get("concerns", [])
        if concerns:
            evaluation_summary += "- 疑虑:\n"
            for c in concerns:
                evaluation_summary += f"  - {c}\n"

    # 从 DB 读取调查计划（含 confirmed 假设）
    plan_str = "无调查计划"
    try:
        async with get_session_factory()() as session:
            incident = await session.get(Incident, uuid.UUID(state["incident_id"]))
            if incident and incident.plan_md:
                plan_str = incident.plan_md
    except Exception:
        pass

    caveat = ""
    if not eval_passed:
        caveat = "注意：自动验证未完全通过，请在报告中如实说明验证情况。"

    user_prompt = SUMMARY_USER_PROMPT.format(
        description=state["description"],
        evaluation_summary=evaluation_summary or "无验证结果",
        investigation_plan=plan_str,
        caveat=caveat,
    )

    # 2. 流式生成报告
    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
    )

    messages = [
        SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    channel = EventPublisher.channel_for_incident(state["incident_id"])
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())

    content = ""
    chunk_count = 0
    t0 = time.monotonic()
    log.info("LLM streaming started", model=s.main_model)

    try:
        async for chunk in llm.astream(messages):
            text = chunk.content if hasattr(chunk, "content") else ""
            if text:
                content += text
                chunk_count += 1
                try:
                    await publisher.publish(
                        channel, "answer", {"content": text, "phase": "investigation"}
                    )
                except Exception:
                    pass
    except Exception as e:
        log.error("LLM streaming failed", error=str(e))
        if not content:
            content = "报告生成失败，请查看调查计划中的假设状态了解排查结果。"
            try:
                await publisher.publish(
                    channel, "answer", {"content": content, "phase": "investigation"}
                )
            except Exception:
                pass

    elapsed = time.monotonic() - t0
    log.info(
        "===== Generate summary completed =====",
        chunks=chunk_count,
        content_len=len(content),
        elapsed=f"{elapsed:.2f}s",
    )

    try:
        await publisher.publish(channel, "answer_done", {"phase": "investigation"})
    except Exception as e:
        log.warning("Failed to publish answer_done", error=str(e))

    return {}
