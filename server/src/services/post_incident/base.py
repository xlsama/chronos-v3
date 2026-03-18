from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from src.config import get_settings


def format_messages_for_extraction(messages: list, description: str) -> str:
    """将 LangChain 消息转为可读文本，供 LLM 提取知识。"""
    lines = [f"事件描述: {description}", ""]
    for msg in messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"[用户] {msg.content}")
        elif isinstance(msg, AIMessage):
            if msg.content:
                lines.append(f"[Agent] {msg.content}")
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    args_str = str(tc.get("args", {}))
                    if len(args_str) > 500:
                        args_str = args_str[:500] + "..."
                    lines.append(f"[Agent 调用工具] {tc['name']}({args_str})")
        elif isinstance(msg, ToolMessage):
            content = msg.content or ""
            if len(content) > 2000:
                content = content[:2000] + "...(truncated)"
            lines.append(f"[工具结果] {content}")
    return "\n".join(lines)


def get_mini_llm() -> ChatOpenAI:
    """获取 mini_model LLM 实例。"""
    s = get_settings()
    return ChatOpenAI(model=s.mini_model, base_url=s.llm_base_url, api_key=s.dashscope_api_key)
