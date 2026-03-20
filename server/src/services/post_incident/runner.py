import asyncio
import time
import uuid

from sqlalchemy import select

from src.db.connection import get_session_factory
from src.db.models import Incident, Message, Server, Service
from src.lib.logger import logger
from src.services.post_incident.base import format_db_messages, get_mini_llm
from src.services.post_incident.agents_md_task import auto_update_agents_md
from src.services.post_incident.history_task import auto_save_history
from src.services.post_incident.skill_evolution_task import auto_evolve_skills

SUMMARIZE_SYSTEM_PROMPT = """你是一个运维报告生成器。根据完整的对话历史，生成结构化的排查报告。

报告格式（Markdown）：

# 事件排查报告

## 事件概要
- 标题: （简明扼要的事件标题）
- 严重程度: （P0/P1/P2/P3）
- 处理状态: （已解决/部分解决/待观察）

## 问题描述
什么服务受影响、症状、影响范围。

## 排查过程
按时间顺序列出关键排查步骤和发现。

## 根因分析
有证据支撑的根本原因分析。

## 修复措施
执行的修复操作及验证结果。

注意事项：
- 基于实际对话内容撰写，不编造未发生的操作或结论
- 使用中文撰写，技术术语保持原文
- 不要在报告末尾添加"报告生成时间"等元信息
"""


def _is_valid_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


async def _build_server_map(messages: list[Message], session) -> dict[str, str]:
    """从 ssh_bash tool_call 中提取 server_id，批量查询 Server 表返回 {id: "name (host)"}。"""
    server_ids: set[str] = set()
    for msg in messages:
        if msg.event_type == "tool_call" and msg.content == "ssh_bash":
            args = (msg.metadata_json or {}).get("args", {})
            sid = args.get("server_id", "")
            if sid:
                server_ids.add(sid)
    if not server_ids:
        return {}

    uuids = [uuid.UUID(s) for s in server_ids if _is_valid_uuid(s)]
    if not uuids:
        return {}

    result = await session.execute(
        select(Server.id, Server.name, Server.host).where(Server.id.in_(uuids))
    )
    return {str(r.id): f"{r.name} ({r.host})" for r in result.all()}


async def _build_service_map(messages: list[Message], session) -> dict[str, str]:
    """从 service_exec tool_call 中提取 service_id，批量查询 Service 表返回 {id: "name (type)"}。"""
    service_ids: set[str] = set()
    for msg in messages:
        if msg.event_type == "tool_call" and msg.content == "service_exec":
            args = (msg.metadata_json or {}).get("args", {})
            sid = args.get("service_id", "")
            if sid:
                service_ids.add(sid)
    if not service_ids:
        return {}

    uuids = [uuid.UUID(s) for s in service_ids if _is_valid_uuid(s)]
    if not uuids:
        return {}

    result = await session.execute(
        select(Service.id, Service.name, Service.service_type).where(Service.id.in_(uuids))
    )
    return {str(r.id): f"{r.name} ({r.service_type})" for r in result.all()}


async def run_post_incident_tasks(incident_id: str, kb_project_id: str | None = None) -> None:
    """后台执行所有事件后任务。从 AgentRunner._post_run() 通过 asyncio.create_task 调用。"""
    sid = incident_id[:8]
    logger.info("[{}] [post_incident] Starting post-incident tasks", sid)

    try:
        t_pipeline = time.monotonic()
        # ① 从 DB 读 Incident + Messages
        t_step = time.monotonic()
        logger.info("[{}] [post_incident] Step① Loading incident and messages from DB", sid)
        async with get_session_factory()() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if not incident:
                logger.error("[{}] [post_incident] Incident not found", sid)
                return
            description = incident.description
            severity = incident.severity

            result = await session.execute(
                select(Message)
                .where(Message.incident_id == uuid.UUID(incident_id))
                .order_by(Message.created_at)
            )
            db_messages = list(result.scalars().all())
            server_map = await _build_server_map(db_messages, session)
            service_map = await _build_service_map(db_messages, session)

        step1_elapsed = time.monotonic() - t_step
        logger.info(
            "[{}] [post_incident] Step① Loaded in {:.2f}s: messages={}, description_len={}, "
            "severity={}, server_map_size={}, service_map_size={}",
            sid,
            step1_elapsed,
            len(db_messages),
            len(description),
            severity,
            len(server_map),
            len(service_map),
        )

        # ② 生成 summary_md（内部变量，不存 Incident 表）
        t_step = time.monotonic()
        conversation_text = format_db_messages(db_messages, description)
        conversation_text_topo = format_db_messages(
            db_messages, description, server_map=server_map, service_map=service_map
        )
        logger.info(
            "[{}] [post_incident] Step② Generating summary, conversation_text_len={}",
            sid,
            len(conversation_text),
        )
        summary_md = await _generate_summary(conversation_text, severity, sid)
        step2_elapsed = time.monotonic() - t_step
        logger.info(
            "[{}] [post_incident] Step② Summary result in {:.2f}s: len={}, preview={!r}",
            sid,
            step2_elapsed,
            len(summary_md),
            summary_md[:100],
        )

        # ③ 生成 title + severity → 写入 DB
        t_step = time.monotonic()
        logger.info("[{}] [post_incident] Step③ Generating title and severity", sid)
        summary_title = None
        new_severity = None
        if summary_md:
            try:
                from src.services.incident_history_service import _generate_title_and_severity
                summary_title, new_severity = await _generate_title_and_severity(summary_md)
                logger.info(
                    "[{}] [post_incident] Step③ Generated: title={!r}, severity={}",
                    sid,
                    summary_title,
                    new_severity,
                )
            except Exception as e:
                logger.opt(exception=True).warning(
                    "[{}] [post_incident] Step③ Title/severity generation failed: {}: {}",
                    sid,
                    type(e).__name__,
                    e,
                )

        if summary_title or new_severity:
            async with get_session_factory()() as session:
                incident = await session.get(Incident, uuid.UUID(incident_id))
                if incident:
                    if summary_title:
                        incident.summary_title = summary_title
                    if new_severity:
                        incident.severity = new_severity
                    await session.commit()
                    logger.info(
                        "[{}] [post_incident] Step③ DB updated: title={!r}, severity={}",
                        sid,
                        summary_title,
                        new_severity,
                    )

        step3_elapsed = time.monotonic() - t_step
        logger.info("[{}] [post_incident] Step③ completed in {:.2f}s", sid, step3_elapsed)

        # ④ 通知
        t_step = time.monotonic()
        logger.info(
            "[{}] [post_incident] Step④ Sending notification: title={!r}, severity={}",
            sid,
            summary_title or description[:80],
            severity,
        )
        from src.services.notification_service import notify_fire_and_forget
        notify_fire_and_forget(
            "resolved", incident_id, summary_title or description[:80],
            severity=severity,
        )
        step4_elapsed = time.monotonic() - t_step
        logger.info("[{}] [post_incident] Step④ Notification sent in {:.2f}s", sid, step4_elapsed)

        # ⑤ 三个子任务并行: history / agents_md / skill_evolution
        t_step = time.monotonic()
        logger.info("[{}] [post_incident] Step⑤ Starting parallel sub-tasks", sid)
        await asyncio.gather(
            _safe_run(auto_save_history(incident_id, summary_md), "history", sid),
            _safe_run(auto_update_agents_md(
                incident_id=incident_id,
                summary_md=summary_md,
                conversation_text=conversation_text_topo,
                kb_project_id=kb_project_id,
            ), "agents_md", sid),
            _safe_run(auto_evolve_skills(
                incident_id=incident_id,
                summary_md=summary_md,
                conversation_text=conversation_text,
            ), "skill_evolution", sid),
        )

        step5_elapsed = time.monotonic() - t_step
        logger.info("[{}] [post_incident] Step⑤ All parallel sub-tasks completed in {:.2f}s", sid, step5_elapsed)
        total_elapsed = time.monotonic() - t_pipeline
        logger.info("[{}] [post_incident] All post-incident tasks completed in {:.2f}s", sid, total_elapsed)
    except Exception as e:
        logger.opt(exception=True).error(
            "[{}] [post_incident] Post-incident tasks failed: {}: {}",
            sid,
            type(e).__name__,
            e,
        )


async def _generate_summary(conversation_text: str, severity: str, sid: str) -> str:
    """用 mini_model 生成 summary_md。"""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = get_mini_llm()
        human_content = (
            f"请根据以下完整对话历史生成排查报告：\n\n"
            f"严重程度: {severity}\n\n"
            f"{conversation_text}"
        )
        logger.info(
            "[{}] [post_incident] _generate_summary: calling LLM, model={}, base_url={}, "
            "system_prompt_len={}, human_content_len={}",
            sid,
            getattr(llm, "model_name", None) or getattr(llm, "model", None),
            getattr(llm, "openai_api_base", None),
            len(SUMMARIZE_SYSTEM_PROMPT),
            len(human_content),
        )
        resp = await llm.ainvoke([
            SystemMessage(content=SUMMARIZE_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ])
        logger.info(
            "[{}] [post_incident] _generate_summary: LLM responded, resp.content type={}, "
            "len={}, preview={!r}",
            sid,
            type(resp.content).__name__,
            len(resp.content) if resp.content else 0,
            resp.content[:200] if resp.content else None,
        )
        summary = resp.content.strip()
        logger.info("[{}] [post_incident] Summary generated ({} chars)", sid, len(summary))
        return summary or "报告生成失败"
    except Exception as e:
        logger.opt(exception=True).error(
            "[{}] [post_incident] Summary generation failed: {}: {}",
            sid,
            type(e).__name__,
            e,
        )
        return f"报告生成失败: {e}"


async def _safe_run(coro, task_name: str, sid: str) -> None:
    """安全执行协程，捕获异常避免影响其他任务。"""
    try:
        result = await coro
        if result is not None:
            logger.info("[{}] [post_incident] {} result: {!r}", sid, task_name, result)
    except Exception as e:
        logger.opt(exception=True).error(
            "[{}] [post_incident] {} failed: {}: {}",
            sid,
            task_name,
            type(e).__name__,
            e,
        )
