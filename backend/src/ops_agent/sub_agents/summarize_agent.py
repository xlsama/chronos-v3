from collections.abc import Callable, Coroutine
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.ops_agent.prompts.summarize import SUMMARIZE_SYSTEM_PROMPT

EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]

_TOOL_OUTPUT_MAX_LEN = 2000


def _format_messages(messages: list, description: str) -> str:
    """Convert LangChain message objects to readable text for the summarize LLM."""
    lines = [f"事件描述: {description}", ""]

    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        elif isinstance(msg, HumanMessage):
            lines.append(f"[用户] {msg.content}")
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    args_str = ", ".join(f"{k}={v!r}" for k, v in tc["args"].items())
                    lines.append(f"[Agent 调用工具] {tc['name']}({args_str})")
            if msg.content:
                lines.append(f"[Agent] {msg.content}")
        elif isinstance(msg, ToolMessage):
            content = str(msg.content)
            if len(content) > _TOOL_OUTPUT_MAX_LEN:
                content = content[:_TOOL_OUTPUT_MAX_LEN] + "\n... (输出已截断)"
            lines.append(f"[工具结果] {content}")

    return "\n".join(lines)


async def run_summarize_agent(
    messages: list,
    description: str,
    severity: str,
    event_callback: EventCallback,
) -> str:
    """Run the summarize sub agent to generate a structured incident report.

    Uses mini_model with streaming. Returns the full markdown report.
    """
    s = get_settings()
    llm = ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        streaming=True,
    )

    conversation_text = _format_messages(messages, description)

    llm_messages = [
        SystemMessage(content=SUMMARIZE_SYSTEM_PROMPT),
        HumanMessage(
            content=f"请根据以下完整对话历史生成排查报告：\n\n"
            f"严重程度: {severity}\n\n"
            f"{conversation_text}"
        ),
    ]

    full_content = ""
    async for chunk in llm.astream(llm_messages):
        if chunk.content:
            full_content += chunk.content
            await event_callback("thinking", {"content": chunk.content})

    return full_content or "报告生成失败"
