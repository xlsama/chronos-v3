import asyncio
import json
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.db.connection import get_session_factory
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.nodes.compact_context import _format_conversation
from src.ops_agent.prompts.planner import (
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_PROMPT,
    UPDATE_PLAN_SYSTEM_PROMPT,
    UPDATE_PLAN_USER_PROMPT,
)
from src.ops_agent.state import OpsState

# 每隔多少次 tool call 触发一次 plan 更新
PLAN_UPDATE_INTERVAL = 6


def _parse_json_response(text: str) -> dict | None:
    """从 LLM 响应中提取 JSON，兼容 markdown code block 包裹。"""
    text = text.strip()
    # 去掉 markdown code block
    if text.startswith("```"):
        lines = text.split("\n")
        # 跳过第一行 (```json) 和最后一行 (```)
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
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def planner_node(state: OpsState) -> dict:
    """生成初始调查计划。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="planner", sid=sid)
    log.info("===== Planner started =====")

    s = get_settings()
    llm = ChatOpenAI(
        model=s.main_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
    )

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

    t0 = time.monotonic()
    response = await asyncio.wait_for(
        llm.ainvoke(
            [
                SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        ),
        timeout=60,
    )
    elapsed = time.monotonic() - t0

    content = response.content if hasattr(response, "content") else str(response)
    plan = _parse_json_response(content)

    if plan is None:
        log.warning("Planner returned invalid JSON, using fallback plan", content=content[:500])
        plan = {
            "symptom_category": "可用性",
            "target_scope": state["description"][:100],
            "hypotheses": [
                {
                    "id": "H1",
                    "description": state["description"],
                    "status": "pending",
                    "priority": 1,
                    "observation_surfaces": ["运行面", "日志面"],
                    "evidence_for": [],
                    "evidence_against": [],
                }
            ],
            "null_hypothesis": None,
            "current_phase": "symptom_classification",
            "next_action": "开始排查",
        }

    log.info(
        "===== Planner completed =====",
        elapsed=f"{elapsed:.2f}s",
        symptom_category=plan.get("symptom_category"),
        hypothesis_count=len(plan.get("hypotheses", [])),
    )
    log.debug("investigation_plan", plan=plan)

    # 发布 plan_generated 事件
    try:
        channel = EventPublisher.channel_for_incident(state["incident_id"])
        publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
        await publisher.publish(
            channel,
            "plan_generated",
            {
                "plan": plan,
                "phase": "planning",
            },
        )
    except Exception as e:
        log.warning("Failed to publish plan_generated event", error=str(e))

    return {
        "investigation_plan": plan,
        "plan_version": 1,
        "tool_call_count_since_plan_update": 0,
    }


async def update_plan_node(state: OpsState) -> dict:
    """根据最近的证据更新调查计划。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="update_plan", sid=sid)

    current_plan = state.get("investigation_plan")
    if not current_plan:
        log.warning("No investigation plan to update, skipping")
        return {"tool_call_count_since_plan_update": 0}

    plan_version = state.get("plan_version", 1)
    log.info("update_plan triggered", plan_version=plan_version)

    # 取最近的消息（距上次更新后的消息）
    messages = state["messages"]
    last_compact = state.get("message_count_at_last_compact", 0)
    recent_messages = messages[max(last_compact, 0) :]
    recent_conversation = _format_conversation(recent_messages[-20:])  # 最多取最近 20 条

    s = get_settings()
    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
    )

    user_prompt = UPDATE_PLAN_USER_PROMPT.format(
        current_plan=json.dumps(current_plan, ensure_ascii=False, indent=2),
        recent_conversation=recent_conversation,
    )

    t0 = time.monotonic()
    response = await asyncio.wait_for(
        llm.ainvoke(
            [
                SystemMessage(content=UPDATE_PLAN_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        ),
        timeout=30,
    )
    elapsed = time.monotonic() - t0

    content = response.content if hasattr(response, "content") else str(response)
    updated_plan = _parse_json_response(content)

    if updated_plan is None:
        log.warning("update_plan returned invalid JSON, keeping current plan")
        return {"tool_call_count_since_plan_update": 0}

    new_version = plan_version + 1
    log.info(
        "update_plan completed",
        elapsed=f"{elapsed:.2f}s",
        new_version=new_version,
    )

    # 发布 plan_updated 事件
    try:
        channel = EventPublisher.channel_for_incident(state["incident_id"])
        publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
        await publisher.publish(
            channel,
            "plan_updated",
            {
                "plan": updated_plan,
                "version": new_version,
                "phase": "investigation",
            },
        )
    except Exception as e:
        log.warning("Failed to publish plan_updated event", error=str(e))

    return {
        "investigation_plan": updated_plan,
        "plan_version": new_version,
        "tool_call_count_since_plan_update": 0,
    }


def should_update_plan(state: OpsState) -> bool:
    """判断是否需要更新调查计划。"""
    if not state.get("investigation_plan"):
        return False
    count = state.get("tool_call_count_since_plan_update", 0)
    return count >= PLAN_UPDATE_INTERVAL
