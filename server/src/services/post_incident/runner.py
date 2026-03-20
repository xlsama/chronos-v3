import asyncio
import time
import uuid

from sqlalchemy import select

from src.db.connection import get_session_factory
from src.db.models import Incident, Message, Server, Service
from src.lib.logger import get_logger
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
    """从 ssh_bash tool_use 中提取 server_id，批量查询 Server 表返回 {id: "name (host)"}。"""
    server_ids: set[str] = set()
    for msg in messages:
        if msg.event_type == "tool_use" and msg.content == "ssh_bash":
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
    """从 service_exec tool_use 中提取 service_id，批量查询 Service 表返回 {id: "name (type)"}。"""
    service_ids: set[str] = set()
    for msg in messages:
        if msg.event_type == "tool_use" and msg.content == "service_exec":
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


async def run_post_incident_tasks(incident_id: str, kb_project_ids: list[str] | None = None) -> None:
    """后台执行所有事件后任务。从 AgentRunner._post_run() 通过 asyncio.create_task 调用。"""
    sid = incident_id[:8]
    log = get_logger(component="post_incident", sid=sid)
    log.info("Starting post-incident tasks")

    try:
        t_pipeline = time.monotonic()
        # ① 从 DB 读 Incident + Messages
        t_step = time.monotonic()
        log.info("Step 1: loading incident and messages from DB")
        async with get_session_factory()() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if not incident:
                log.error("Incident not found")
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
        log.info(
            "Step 1: loaded from DB",
            elapsed=f"{step1_elapsed:.2f}s",
            messages=len(db_messages),
            description_len=len(description),
            severity=severity,
            server_map_size=len(server_map),
            service_map_size=len(service_map),
        )

        # ② 生成 summary_md（内部变量，不存 Incident 表）
        t_step = time.monotonic()
        conversation_text = format_db_messages(db_messages, description)
        conversation_text_topo = format_db_messages(
            db_messages, description, server_map=server_map, service_map=service_map
        )
        log.info("Step 2: generating summary", conversation_text_len=len(conversation_text))
        summary_md = await _generate_summary(conversation_text, severity, sid)
        step2_elapsed = time.monotonic() - t_step
        log.info(
            "Step 2: summary generated",
            elapsed=f"{step2_elapsed:.2f}s",
            summary_len=len(summary_md),
            preview=summary_md[:100],
        )

        # ③ 生成 title + severity → 写入 DB
        t_step = time.monotonic()
        log.info("Step 3: generating title and severity")
        summary_title = None
        new_severity = None
        if summary_md:
            try:
                from src.services.incident_history_service import _generate_title_and_severity
                summary_title, new_severity = await _generate_title_and_severity(summary_md)
                log.info(
                    "Step 3: generated title and severity",
                    title=summary_title,
                    severity=new_severity,
                )
            except Exception:
                log.warning("Step 3: title/severity generation failed", exc_info=True)

        if summary_title or new_severity:
            async with get_session_factory()() as session:
                incident = await session.get(Incident, uuid.UUID(incident_id))
                if incident:
                    if summary_title:
                        incident.summary_title = summary_title
                    if new_severity:
                        incident.severity = new_severity
                    await session.commit()
                    log.info(
                        "Step 3: DB updated",
                        title=summary_title,
                        severity=new_severity,
                    )

        step3_elapsed = time.monotonic() - t_step
        log.info("Step 3: completed", elapsed=f"{step3_elapsed:.2f}s")

        # ④ 通知
        t_step = time.monotonic()
        log.info(
            "Step 4: sending notification",
            title=summary_title or description[:80],
            severity=severity,
        )
        from src.services.notification_service import notify_fire_and_forget
        notify_fire_and_forget(
            "resolved", incident_id, summary_title or description[:80],
            severity=severity,
        )
        step4_elapsed = time.monotonic() - t_step
        log.info("Step 4: notification sent", elapsed=f"{step4_elapsed:.2f}s")

        # ⑤ 三个子任务并行: history / agents_md / skill_evolution
        t_step = time.monotonic()
        log.info("Step 5: starting parallel sub-tasks")
        await asyncio.gather(
            _safe_run(auto_save_history(incident_id, summary_md), "history", sid),
            _safe_run(auto_update_agents_md(
                incident_id=incident_id,
                summary_md=summary_md,
                conversation_text=conversation_text_topo,
                kb_project_ids=kb_project_ids,
            ), "agents_md", sid),
            _safe_run(auto_evolve_skills(
                incident_id=incident_id,
                summary_md=summary_md,
                conversation_text=conversation_text,
            ), "skill_evolution", sid),
        )

        step5_elapsed = time.monotonic() - t_step
        log.info("Step 5: all parallel sub-tasks completed", elapsed=f"{step5_elapsed:.2f}s")
        total_elapsed = time.monotonic() - t_pipeline
        log.info("All post-incident tasks completed", elapsed=f"{total_elapsed:.2f}s")
    except Exception:
        log.error("Post-incident tasks failed", exc_info=True)


async def _generate_summary(conversation_text: str, severity: str, sid: str) -> str:
    """用 mini_model 生成 summary_md。"""
    log = get_logger(component="post_incident", sid=sid)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = get_mini_llm()
        human_content = (
            f"请根据以下完整对话历史生成排查报告：\n\n"
            f"严重程度: {severity}\n\n"
            f"{conversation_text}"
        )
        log.info(
            "Generating summary: calling LLM",
            model=getattr(llm, "model_name", None) or getattr(llm, "model", None),
            base_url=getattr(llm, "openai_api_base", None),
            system_prompt_len=len(SUMMARIZE_SYSTEM_PROMPT),
            human_content_len=len(human_content),
        )
        resp = await llm.ainvoke([
            SystemMessage(content=SUMMARIZE_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ])
        log.info(
            "Generating summary: LLM responded",
            resp_content_type=type(resp.content).__name__,
            resp_len=len(resp.content) if resp.content else 0,
            preview=resp.content[:200] if resp.content else None,
        )
        summary = resp.content.strip()
        log.info("Summary generated", chars=len(summary))
        return summary or "报告生成失败"
    except Exception:
        log.error("Summary generation failed", exc_info=True)
        return f"报告生成失败"


async def _safe_run(coro, task_name: str, sid: str) -> None:
    """安全执行协程，捕获异常避免影响其他任务。"""
    log = get_logger(component="post_incident", sid=sid)
    try:
        result = await coro
        if result is not None:
            log.info("Sub-task completed", task=task_name, result=result)
    except Exception:
        log.error("Sub-task failed", task=task_name, exc_info=True)
