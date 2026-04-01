"""工具输出截断 —— 防止大输出膨胀 LLM context。"""

from typing import Any

DEFAULT_MAX_CHARS = 30_000


def truncate_output(result: Any, max_chars: int = DEFAULT_MAX_CHARS) -> Any:
    """截断工具输出。支持 str 和 dict（含 stdout/stderr 字段）两种格式。"""
    if max_chars <= 0:
        return result

    if isinstance(result, str):
        return _truncate_str(result, max_chars)

    if isinstance(result, dict):
        return _truncate_dict(result, max_chars)

    return result


def _truncate_str(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[输出已截断，原始 {len(text)} 字符，显示前 {max_chars} 字符]"


def _truncate_dict(data: dict, max_chars: int) -> dict:
    """截断 dict 中的长文本字段（stdout / output / stderr）。"""
    truncated = False
    result = data

    for key in ("stdout", "output", "stderr"):
        val = data.get(key)
        if isinstance(val, str) and len(val) > max_chars:
            if not truncated:
                result = {**data}  # shallow copy on first truncation
                truncated = True
            result[key] = _truncate_str(val, max_chars)

    return result
