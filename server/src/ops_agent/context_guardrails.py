from collections.abc import Sequence

def build_context_request_question(unknown_tools: Sequence[str] | None = None) -> str:
    """Return a stable clarification prompt for under-specified incidents."""
    lines = []
    if unknown_tools:
        rendered = ", ".join(f"`{name}`" for name in unknown_tools if name)
        if rendered:
            lines.append(
                f"当前信息不足，Agent 尝试调用未注册工具 {rendered}，无法直接开始排查。"
            )
    if not lines:
        lines.append("当前信息不足，无法直接开始排查。")

    lines.extend([
        "请补充以下信息后我再继续：",
        "- 具体故障现象或完整报错",
        "- 受影响的服务、系统或接口",
        "- 发生时间或时间段",
        "- 最近变更、发布或已做过的操作",
    ])
    return "\n".join(lines)
