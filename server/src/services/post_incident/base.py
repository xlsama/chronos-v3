from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.db.models import Message


def format_db_messages(messages: list[Message], description: str) -> str:
    """将 DB Message 记录转为可读文本，供 LLM 生成 summary / 提取知识。"""
    lines = [f"事件描述: {description}", ""]
    for msg in messages:
        role = msg.role
        event_type = msg.event_type
        content = msg.content or ""

        if role == "user":
            lines.append(f"[用户] {content}")
        elif role == "assistant":
            if event_type == "tool_call":
                # content 是工具名称，metadata_json 包含参数
                args = msg.metadata_json or {}
                args_str = str(args)
                if len(args_str) > 500:
                    args_str = args_str[:500] + "..."
                lines.append(f"[Agent 调用工具] {content}({args_str})")
            elif event_type == "tool_result":
                if len(content) > 2000:
                    content = content[:2000] + "...(truncated)"
                lines.append(f"[工具结果] {content}")
            elif event_type in ("thinking", "answer"):
                if content:
                    lines.append(f"[Agent] {content}")
    return "\n".join(lines)


def get_mini_llm() -> ChatOpenAI:
    """获取 mini_model LLM 实例。"""
    s = get_settings()
    return ChatOpenAI(model=s.mini_model, base_url=s.llm_base_url, api_key=s.dashscope_api_key)
