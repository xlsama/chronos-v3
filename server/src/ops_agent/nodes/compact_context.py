import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from src.db.connection import get_session_factory
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.prompts.compact import COMPACT_SYSTEM_PROMPT, COMPACT_USER_PROMPT
from src.ops_agent.state import OpsState

# 每次 tool call/response 约 11-12k tokens，30 条消息 ≈ 15 轮 tool call
COMPACT_THRESHOLD = 100
# 最多压缩 5 次，之后不再压缩
MAX_COMPACT_COUNT = 5

def _format_message_for_summary(msg) -> str:
    """将单条消息格式化为可读文本，用于压缩摘要。"""
    if isinstance(msg, SystemMessage):
        return ""  # 跳过 system message
    if isinstance(msg, HumanMessage):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        return f"[用户] {content}"
    if isinstance(msg, AIMessage):
        parts = []
        if msg.content:
            parts.append(f"[Agent 思考] {msg.content[:500]}")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name", "unknown")
                args = tc.get("args", {})
                # 只保留关键参数
                if name in ("ssh_bash", "bash"):
                    parts.append(f"[调用 {name}] {args.get('command', '')}")
                elif name == "service_exec":
                    parts.append(f"[调用 service_exec] {args.get('command', '')}")
                elif name == "ask_human":
                    parts.append(f"[调用 ask_human] {args.get('question', '')}")
                elif name == "update_plan":
                    parts.append(f"[调用 update_plan] {args.get('plan_md', '')[:200]}")
                else:
                    parts.append(f"[调用 {name}] {args}")
        return "\n".join(parts) if parts else ""
    if isinstance(msg, ToolMessage):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        # 截断过长的 tool 输出
        if len(content) > 2000:
            content = content[:2000] + "\n... (已截断)"
        return f"[工具结果] {content}"
    return ""


def _format_conversation(messages: list) -> str:
    """将消息列表格式化为可读的对话记录。"""
    return "\n\n".join(
        formatted for msg in messages if (formatted := _format_message_for_summary(msg))
    )


async def compact_context_node(state: OpsState) -> dict:
    """压缩上下文：用 mini_model 将累积的消息生成结构化摘要，替换原消息列表。"""
    sid = state["incident_id"][:8]
    log = get_logger(component="compact_context", sid=sid)

    messages = state["messages"]
    compact_count = state.get("compact_count", 0)
    description = state["description"]

    log.info(
        "compact_context_node triggered",
        message_count=len(messages),
        compact_count=compact_count,
    )

    # 判断触发原因：假设状态变更 or 消息数超限
    is_hypothesis_transition = False
    for msg in reversed(messages):
        if hasattr(msg, "tool_call_id") and "假设状态已变更" in (
            getattr(msg, "content", None) or ""
        ):
            is_hypothesis_transition = True
            break
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            break
    reason = "hypothesis_transition" if is_hypothesis_transition else "message_limit"

    # 初始化 publisher（round_started / round_ended 都需要）
    channel = EventPublisher.channel_for_incident(state["incident_id"])
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())

    # 只在假设状态变更时发布 round_started 事件
    # message_limit 触发的压缩是静默的，不向前端发送任何事件
    if is_hypothesis_transition:
        try:
            await publisher.publish(
                channel,
                "round_started",
                {
                    "round": compact_count + 1,
                    "reason": reason,
                    "phase": "investigation",
                },
            )
        except Exception as e:
            log.warning("Failed to publish round_started event", error=str(e))

    # 格式化对话记录（跳过第一条 HumanMessage，它是事件描述，会单独传入）
    conversation = _format_conversation(messages[1:])

    # 调用 mini_model 生成摘要
    s = get_settings()
    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
    )

    user_prompt = COMPACT_USER_PROMPT.format(
        description=description,
        conversation=conversation,
    )

    t0 = time.monotonic()
    response = await llm.ainvoke(
        [
            SystemMessage(content=COMPACT_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
    )
    elapsed = time.monotonic() - t0

    summary = response.content
    log.info(
        "compact_context completed",
        elapsed=f"{elapsed:.2f}s",
        summary_chars=len(summary),
        original_messages=len(messages),
    )

    # 构建压缩后的消息列表：
    # 1. 保留原始 HumanMessage（事件描述）
    # 2. 插入摘要作为 SystemMessage
    first_human_msg = messages[0]
    compacted_messages = [
        first_human_msg,
        SystemMessage(content=f"## 排查进度摘要（第 {compact_count + 1} 次压缩）\n\n{summary}"),
    ]

    result: dict = {
        "messages": compacted_messages,
        "investigation_summary": summary,
        "message_count_at_last_compact": len(compacted_messages),
        "compact_count": compact_count + 1,
    }

    # 只有假设切换才发 round_ended + 递增轮次
    # 消息过多触发的 compact 只压缩，不发事件
    if is_hypothesis_transition:
        current_round = state.get("investigation_round", 1)
        max_rounds = get_settings().max_investigation_rounds
        log.info(
            "Hypothesis transition, ending round",
            round=current_round,
            max_rounds=max_rounds,
        )
        try:
            await publisher.publish(
                channel,
                "round_ended",
                {
                    "round": current_round,
                    "summary": summary[:500],
                    "phase": "investigation",
                },
            )
        except Exception as e:
            log.warning("Failed to publish round_ended event", error=str(e))
        next_round = current_round + 1
        if next_round > max_rounds:
            log.warning("Max investigation rounds reached", max_rounds=max_rounds)
        result["investigation_round"] = next_round

    return result


def should_compact(state: OpsState) -> bool:
    """判断是否需要压缩上下文。"""
    compact_count = state.get("compact_count", 0)
    if compact_count >= MAX_COMPACT_COUNT:
        return False

    msg_count = len(state["messages"])
    last_compact = state.get("message_count_at_last_compact", 0)
    return (msg_count - last_compact) > COMPACT_THRESHOLD
