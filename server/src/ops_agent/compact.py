"""上下文压缩（compact）核心逻辑。

当 Agent 消息累积超过 LLM token 限制时，用 mini_model 总结对话历史，
清除旧消息并以压缩摘要继续排查。主 Agent 和子 Agent 共用此模块。
"""

import time
import uuid

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.db.connection import get_session_factory
from src.db.models import Incident
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.state import HypothesisResult

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

MAIN_COMPACT_SYSTEM_PROMPT = """\
你是运维排查进展总结助手。请根据提供的排查上下文，生成一份结构化的排查进展摘要。

这份摘要将作为后续排查的唯一上下文，必须包含所有关键信息，确保排查能无缝继续。

请先在 <analysis> 标签中整理思路，然后在 <summary> 标签中输出最终摘要。

<summary> 必须包含以下部分：

1. **事件概述**: 事件描述和严重程度
2. **已验证的假设**: 每个假设的验证结果、关键证据和结论
3. **已执行的排查操作**: 关键命令和发现（保留命令原文和关键输出）
4. **已执行的修复操作**: 修复命令、验证方式和结果
5. **用户反馈**: 用户提供的所有反馈和额外信息
6. **当前排查状态**: 正在进行的工作和最新进展
7. **下一步方向**: 接下来应该做什么

示例输出格式：

<analysis>
[整理排查过程中的关键信息，确保不遗漏]
</analysis>

<summary>
1. **事件概述**:
   [描述]

2. **已验证的假设**:
   - H1 [已排除] xxx: 结论...
   - H2 [已确认] xxx: 结论...

3. **已执行的排查操作**:
   - `docker ps -a` → 发现...
   - `service_exec` 查询连接数 → 23/200

4. **已执行的修复操作**:
   - 执行 `docker restart xxx` → 服务恢复

5. **用户反馈**:
   - 用户反馈: "页面还是没有数据"

6. **当前排查状态**:
   [描述]

7. **下一步方向**:
   [描述]
</summary>
"""

INVESTIGATION_COMPACT_SYSTEM_PROMPT = """\
你是运维排查进展总结助手。请总结以下单个假设的排查进展。

这份摘要将作为后续排查的唯一上下文，确保排查能无缝继续。

请先在 <analysis> 标签中整理思路，然后在 <summary> 标签中输出最终摘要。

<summary> 必须包含以下部分：

1. **假设与目标**: 假设描述和排查目标
2. **已执行的命令和查询**: 关键操作及其结果（保留命令原文和关键输出）
3. **发现的关键线索**: 重要的诊断信息和证据
4. **当前判断**: 假设是否可能成立的倾向和依据
5. **下一步排查方向**: 接下来应该检查什么

示例输出格式：

<analysis>
[整理排查链路中的关键信息]
</analysis>

<summary>
1. **假设与目标**:
   [描述]

2. **已执行的命令和查询**:
   - `docker logs --tail 200 xxx` → 发现 OOM 错误
   - `service_exec` 查询慢查询 → 无异常

3. **发现的关键线索**:
   - [线索1]
   - [线索2]

4. **当前判断**:
   [描述]

5. **下一步排查方向**:
   [描述]
</summary>
"""


# ---------------------------------------------------------------------------
# Helper: context limit error detection
# ---------------------------------------------------------------------------


def is_context_limit_error(e: Exception) -> bool:
    """Check if the error is a context/input length limit error from the LLM API."""
    s = str(e).lower()
    return (
        "input length" in s
        or "context_length_exceeded" in s
        or "prompt is too long" in s
        or "maximum context length" in s
    )


# ---------------------------------------------------------------------------
# Helper: build compact input from structured data + recent messages
# ---------------------------------------------------------------------------


def _format_hypothesis_results(results: list[HypothesisResult]) -> str:
    if not results:
        return "暂无已完成的假设验证。"
    status_zh = {"confirmed": "已确认", "eliminated": "已排除", "inconclusive": "证据不足"}
    lines = []
    for r in results:
        s = status_zh.get(r["status"], r["status"])
        lines.append(f"- {r['hypothesis_id']} [{s}] {r['hypothesis_desc']}: {r['summary']}")
    return "\n".join(lines)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n...[内容已截断]...\n" + text[-half:]


def _format_recent_messages(messages: list[BaseMessage], max_total_chars: int) -> str:
    """从后向前取消息，总字符数不超过 max_total_chars。"""
    parts: list[str] = []
    total = 0
    for msg in reversed(messages):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        role = msg.type  # "human", "ai", "tool", "system"
        truncated = _truncate(content, 3000)
        entry = f"[{role}] {truncated}"
        if total + len(entry) > max_total_chars:
            break
        parts.append(entry)
        total += len(entry)
    parts.reverse()
    return "\n\n".join(parts) if parts else "（无最近消息）"


def _build_main_compact_input(
    description: str,
    severity: str,
    hypothesis_results: list[HypothesisResult],
    plan_md: str,
    messages: list[BaseMessage],
    max_recent_chars: int,
) -> str:
    return (
        f"## 事件信息\n"
        f"- 描述: {description}\n"
        f"- 严重程度: {severity}\n\n"
        f"## 当前调查计划\n{plan_md or '暂无调查计划'}\n\n"
        f"## 已完成的假设验证\n{_format_hypothesis_results(hypothesis_results)}\n\n"
        f"## 最近的排查对话\n{_format_recent_messages(messages, max_recent_chars)}"
    )


def _build_investigation_compact_input(
    hypothesis_id: str,
    hypothesis_desc: str,
    description: str,
    severity: str,
    messages: list[BaseMessage],
    max_recent_chars: int,
) -> str:
    return (
        f"## 假设信息\n"
        f"假设 {hypothesis_id}: {hypothesis_desc}\n\n"
        f"## 事件背景\n"
        f"- 描述: {description}\n"
        f"- 严重程度: {severity}\n\n"
        f"## 排查对话\n{_format_recent_messages(messages, max_recent_chars)}"
    )


# ---------------------------------------------------------------------------
# Helper: format compact summary (strip <analysis>, extract <summary>)
# ---------------------------------------------------------------------------


def _format_compact_summary(raw: str) -> str:
    """Strip <analysis> scratchpad and extract <summary> content."""
    import re

    # Remove <analysis>...</analysis>
    cleaned = re.sub(r"<analysis>[\s\S]*?</analysis>", "", raw, count=1)
    # Extract <summary>...</summary>
    m = re.search(r"<summary>([\s\S]*?)</summary>", cleaned)
    if m:
        return m.group(1).strip()
    # Fallback: return cleaned text without tags
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Core: compact_conversation
# ---------------------------------------------------------------------------


async def compact_conversation(
    *,
    messages: list[BaseMessage],
    system_prompt: str,
    user_prompt: str,
    incident_id: str,
    publisher: EventPublisher,
    channel: str,
    phase: str = "investigation",
    agent_type: str = "main",
) -> str:
    """Call mini_model to generate a compact summary.

    Streams thinking tokens to the frontend via EventPublisher.
    Falls back to a no-LLM summary if the mini_model also fails.

    Returns the formatted compact_md string.
    """
    s = get_settings()
    sid = incident_id[:8]
    log = get_logger(component="compact", sid=sid)

    # Publish compact_start
    await publisher.publish(
        channel,
        "compact_start",
        {"phase": phase, "agent_type": agent_type},
    )

    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
        extra_body={"enable_thinking": False},
    )

    llm_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    content = ""
    t0 = time.monotonic()
    try:
        async for chunk in llm.astream(llm_messages):
            text = chunk.content if hasattr(chunk, "content") else ""
            if text:
                content += text
                try:
                    await publisher.publish(
                        channel,
                        "thinking",
                        {"content": text, "phase": "compact"},
                    )
                except Exception:
                    pass

        elapsed = time.monotonic() - t0
        log.info("Compact LLM completed", elapsed=f"{elapsed:.2f}s", chars=len(content))

        # Flush thinking and publish thinking_done
        try:
            await publisher.publish(channel, "thinking_done", {"phase": "compact"})
        except Exception:
            pass

        summary = _format_compact_summary(content)
        if not summary:
            log.warning("Compact LLM returned empty summary, using raw content")
            summary = content.strip() or "排查进展摘要生成失败，请根据调查计划继续排查。"

    except Exception as e:
        log.warning("Compact LLM failed, using fallback", error=str(e))
        # Fallback: just use the user_prompt as-is (it contains structured data)
        summary = f"（自动摘要失败，以下是结构化排查数据）\n\n{user_prompt}"

    # Publish compact_done
    await publisher.publish(
        channel,
        "compact_done",
        {"phase": phase, "compact_md": summary[:500]},
    )

    return summary


# ---------------------------------------------------------------------------
# Public: compact for main agent
# ---------------------------------------------------------------------------


async def compact_main_agent(
    *,
    incident_id: str,
    description: str,
    severity: str,
    hypothesis_results: list[HypothesisResult],
    messages: list[BaseMessage],
) -> str:
    """Compact the main agent's conversation.

    Reads plan_md from DB, builds structured input, calls mini_model.
    Returns the compact_md summary.
    """
    s = get_settings()

    # Read current plan from DB
    plan_md = ""
    try:
        async with get_session_factory()() as session:
            incident = await session.get(Incident, uuid.UUID(incident_id))
            if incident and incident.plan_md:
                plan_md = incident.plan_md
    except Exception:
        pass

    user_prompt = _build_main_compact_input(
        description=description,
        severity=severity,
        hypothesis_results=hypothesis_results,
        plan_md=plan_md,
        messages=messages,
        max_recent_chars=s.max_compact_recent_chars,
    )

    channel = EventPublisher.channel_for_incident(incident_id)
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())

    return await compact_conversation(
        messages=messages,
        system_prompt=MAIN_COMPACT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        incident_id=incident_id,
        publisher=publisher,
        channel=channel,
        phase="investigation",
        agent_type="main",
    )


# ---------------------------------------------------------------------------
# Public: compact for investigation agent
# ---------------------------------------------------------------------------


async def compact_investigation_agent(
    *,
    incident_id: str,
    description: str,
    severity: str,
    hypothesis_id: str,
    hypothesis_desc: str,
    messages: list[BaseMessage],
) -> str:
    """Compact the investigation agent's conversation.

    Returns the compact_md summary.
    """
    s = get_settings()

    user_prompt = _build_investigation_compact_input(
        hypothesis_id=hypothesis_id,
        hypothesis_desc=hypothesis_desc,
        description=description,
        severity=severity,
        messages=messages,
        max_recent_chars=s.max_compact_recent_chars,
    )

    channel = EventPublisher.channel_for_incident(incident_id)
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())

    return await compact_conversation(
        messages=messages,
        system_prompt=INVESTIGATION_COMPACT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        incident_id=incident_id,
        publisher=publisher,
        channel=channel,
        phase="investigation",
        agent_type="investigation",
    )
