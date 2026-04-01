"""子 Agent SSE 事件桥接 —— 将子 Agent 事件转发到前端 SSE channel。"""

from src.lib.logger import get_logger
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.tools.normalization import normalize_tool_output


async def bridge_event(
    event: dict,
    channel: str,
    publisher: EventPublisher,
    hypothesis_id: str,
    thinking_buffer: str,
    ask_human_active: bool,
    ask_human_streamed: bool,
    approval_id: str = "",
    approval_tool_name: str = "",
) -> dict:
    """桥接子 Agent 事件到 SSE channel，附加 sub_agent_id。

    返回更新后的状态 dict (thinking_buffer, ask_human_active, ask_human_streamed,
    approval_id, approval_tool_name)。
    """
    log = get_logger(component="bridge_event")
    kind = event.get("event")
    metadata = event.get("metadata", {})
    node = metadata.get("langgraph_node", "")

    if node in ("human_approval", "ask_human", "retry_tool_call"):
        return {
            "thinking_buffer": thinking_buffer,
            "ask_human_active": ask_human_active,
            "ask_human_streamed": ask_human_streamed,
            "approval_id": approval_id,
            "approval_tool_name": approval_tool_name,
        }

    try:
        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tcc in chunk.tool_call_chunks:
                    if tcc.get("name") == "conclude":
                        await publisher.publish(
                            channel,
                            "sub_agent_reporting",
                            {"hypothesis_id": hypothesis_id, "phase": "investigation"},
                        )
            if chunk and chunk.content and not ask_human_active:
                thinking_buffer += chunk.content
                await publisher.publish(
                    channel,
                    "thinking",
                    {
                        "content": chunk.content,
                        "phase": "investigation",
                        "sub_agent_id": hypothesis_id,
                    },
                )

        elif kind == "on_chat_model_end":
            if not ask_human_active:
                thinking_buffer = ""
                await publisher.publish(
                    channel,
                    "thinking_done",
                    {"phase": "investigation", "sub_agent_id": hypothesis_id},
                )

        elif kind == "on_tool_start":
            name = event.get("name", "")
            if name in ("conclude", "ask_human", "read_skill"):
                pass
            else:
                run_id = event.get("run_id", "")
                tool_use_data: dict = {
                    "name": name,
                    "args": event["data"].get("input", {}),
                    "tool_call_id": run_id,
                    "phase": "investigation",
                    "sub_agent_id": hypothesis_id,
                }
                # 标记已批准的 tool_use 事件
                if approval_id and name == approval_tool_name:
                    tool_use_data["approval_id"] = approval_id
                await publisher.publish(channel, "tool_use", tool_use_data)

        elif kind == "on_tool_end":
            name = event.get("name", "")
            if name in ("conclude", "ask_human"):
                pass
            elif name == "read_skill":
                args = event["data"].get("input", {})
                output, _ = normalize_tool_output(event["data"].get("output", ""))
                success = not output.startswith("未找到")
                parts = args.get("path", "").split("/", 1)
                slug = parts[0]
                file_path = parts[1] if len(parts) > 1 else None
                await publisher.publish(
                    channel,
                    "skill_read",
                    {
                        "skill_slug": slug,
                        "skill_name": file_path or slug,
                        "content": output,
                        "success": success,
                        "phase": "investigation",
                        "sub_agent_id": hypothesis_id,
                    },
                )
            else:
                run_id = event.get("run_id", "")
                output_raw = event["data"].get("output", "")
                output_str, status = normalize_tool_output(output_raw)
                tool_result_data: dict = {
                    "name": name,
                    "output": output_str,
                    "tool_call_id": run_id,
                    "status": status,
                    "phase": "investigation",
                    "sub_agent_id": hypothesis_id,
                }
                # 标记已批准的 tool_result 事件，并清除 approval 标记
                if approval_id and name == approval_tool_name:
                    tool_result_data["approval_id"] = approval_id
                    approval_id = ""
                    approval_tool_name = ""
                await publisher.publish(channel, "tool_result", tool_result_data)
    except Exception as e:
        log.warning(
            "Failed to bridge sub-agent event",
            kind=kind,
            hypothesis=hypothesis_id,
            error=str(e),
        )

    return {
        "thinking_buffer": thinking_buffer,
        "ask_human_active": ask_human_active,
        "ask_human_streamed": ask_human_streamed,
        "approval_id": approval_id,
        "approval_tool_name": approval_tool_name,
    }
