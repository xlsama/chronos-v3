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
from src.ops_agent.prompts.planner import PLANNER_SYSTEM_PROMPT, PLANNER_USER_PROMPT
from src.ops_agent.state import CoordinatorState


async def planner_node(state: CoordinatorState) -> dict:
    """生成初始调查计划（Markdown 格式）。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="planner", sid=sid)
    log.info("===== Planner started =====")

    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
        extra_body={"enable_thinking": s.planner_thinking},
    )

    # 发布 planner_started 事件，让前端立即切换到 planning 阶段
    channel = EventPublisher.channel_for_incident(state["incident_id"])
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
    try:
        await publisher.publish(channel, "planner_started", {"phase": "planning"})
    except Exception as e:
        log.warning("Failed to publish planner_started event", error=str(e))

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

    user_prompt = PLANNER_USER_PROMPT.format(
        description=state["description"],
        severity=state["severity"],
        history_context=history_context,
        kb_context=kb_context,
    )

    # 使用 astream 流式调用 LLM，同时推送 thinking 事件到前端
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]
    prompt_chars = sum(len(m.content) for m in messages if hasattr(m, "content"))
    log.info("LLM call starting", model=s.main_model, prompt_chars=prompt_chars)

    try:
        await publisher.publish(
            channel, "planner_progress", {"status": "llm_call_started", "phase": "planning"}
        )
    except Exception as e:
        log.warning("Failed to publish planner_progress event", error=str(e))

    content = ""
    first_token_time = None
    chunk_count = 0
    publish_errors = 0
    t0 = time.monotonic()
    async for chunk in llm.astream(messages):
        text = chunk.content if hasattr(chunk, "content") else ""
        if text:
            chunk_count += 1
            content += text
            if first_token_time is None:
                first_token_time = time.monotonic()
                ttft = first_token_time - t0
                log.info("First token received", ttft=f"{ttft:.2f}s")
                try:
                    await publisher.publish(
                        channel,
                        "planner_progress",
                        {
                            "status": "first_token_received",
                            "ttft": round(ttft, 2),
                            "phase": "planning",
                        },
                    )
                except Exception as e:
                    log.warning("Failed to publish first_token progress", error=str(e))
            if chunk_count % 10 == 0:
                log.debug(
                    "Streaming progress",
                    chunks=chunk_count,
                    chars=len(content),
                    elapsed=f"{time.monotonic() - t0:.1f}s",
                )
            try:
                await publisher.publish(channel, "thinking", {"content": text, "phase": "planning"})
            except Exception as e:
                publish_errors += 1
                if publish_errors <= 3:
                    log.warning(
                        "Failed to publish thinking event",
                        error=str(e),
                        chunk=chunk_count,
                    )
    elapsed = time.monotonic() - t0
    ttft_str = f"{first_token_time - t0:.2f}s" if first_token_time else "no_tokens"
    log.info(
        "LLM streaming completed",
        elapsed=f"{elapsed:.2f}s",
        ttft=ttft_str,
        chunks=chunk_count,
        chars=len(content),
        publish_errors=publish_errors,
    )
    try:
        await publisher.publish(channel, "thinking_done", {"phase": "planning"})
    except Exception as e:
        log.warning("Failed to publish thinking_done event", error=str(e))

    # 清理可能的 code block 包裹
    plan_md = content.strip()
    if plan_md.startswith("```"):
        lines = plan_md.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        plan_md = "\n".join(lines).strip()

    log.info("===== Planner completed =====", elapsed=f"{elapsed:.2f}s", plan_chars=len(plan_md))
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
