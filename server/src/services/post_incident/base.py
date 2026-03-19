from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.db.models import Message


def format_db_messages(
    messages: list[Message],
    description: str,
    server_map: dict[str, str] | None = None,
) -> str:
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
                metadata = msg.metadata_json or {}
                tool_name = content  # msg.content 即工具名

                if server_map and tool_name == "bash":
                    args = metadata.get("args", {})
                    server_id = args.get("server_id", "")
                    command = args.get("command", "")
                    server_label = server_map.get(server_id, server_id)
                    if len(command) > 400:
                        command = command[:400] + "..."
                    lines.append(f"[Agent 在 {server_label} 上执行] {command}")
                else:
                    args_str = str(metadata)
                    if len(args_str) > 500:
                        args_str = args_str[:500] + "..."
                    lines.append(f"[Agent 调用工具] {tool_name}({args_str})")
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
    return ChatOpenAI(
        model=s.mini_model,
        base_url=s.llm_base_url,
        api_key=s.dashscope_api_key,
        extra_body={"enable_thinking": False},
    )
