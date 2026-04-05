"""Tool output 规范化 —— 从 LangGraph on_tool_end 事件中提取工具输出的唯一入口。"""

import json
from typing import Any

from langchain_core.messages import ToolMessage

from src.ops_agent.tools.truncation import truncate_output

# SSE 事件桥中输出截断阈值（字符），防止过大的 tool_result 事件
_SSE_OUTPUT_MAX_CHARS = 50_000


def normalize_tool_output(raw: Any, max_chars: int = _SSE_OUTPUT_MAX_CHARS) -> tuple[str, str]:
    """从 LangGraph on_tool_end 事件中提取工具输出。

    Returns:
        (output_str, status)
        - output_str: 干净的字符串（dict/list 会 JSON 序列化，str 保持原样），超长时截断
        - status: "success" | "error"
    """
    # Step 1: 从 ToolMessage 中解包 content
    content = raw.content if isinstance(raw, ToolMessage) else raw

    # Step 2: 确保 content 是字符串
    if isinstance(content, (dict, list)):
        output_str = json.dumps(content, ensure_ascii=False)
    elif isinstance(content, str):
        output_str = content
    else:
        output_str = str(content)

    # Step 3: 截断过长输出
    output_str = truncate_output(output_str, max_chars)

    # Step 4: 判断 status
    status = _determine_status(output_str)
    return output_str, status


def _determine_status(output_str: str) -> str:
    """根据输出内容判断工具执行状态。"""
    try:
        parsed = json.loads(output_str)
    except (json.JSONDecodeError, ValueError, TypeError):
        # 纯文本：检查错误前缀
        if output_str.startswith(("错误:", "执行异常:", "执行失败:", "命令被系统拦截")):
            return "error"
        return "success"

    if isinstance(parsed, dict):
        if parsed.get("error"):
            return "error"
        if parsed.get("exit_code") not in (None, 0):
            return "error"

    return "success"
