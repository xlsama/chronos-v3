"""子 Agent 生命周期管理节点 —— 创建/恢复子 Agent，桥接 SSE 事件。"""

import uuid

from langchain_core.messages import HumanMessage

from src.db.connection import get_session_factory
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.investigation_graph import compile_investigation_graph
from src.ops_agent.state import CoordinatorState, HypothesisResult


def _format_prior_findings(results: list[HypothesisResult]) -> str:
    """将之前子 Agent 的调查结果格式化为上下文。"""
    if not results:
        return ""
    lines = []
    for r in results:
        status_map = {"confirmed": "已确认", "eliminated": "已排除", "inconclusive": "证据不足"}
        status_zh = status_map.get(r["status"], r["status"])
        lines.append(f"- {r['hypothesis_id']} [{status_zh}] {r['hypothesis_desc']}: {r['summary']}")
    return "\n".join(lines)


async def run_sub_agent_node(state: CoordinatorState) -> dict:
    """创建或恢复子 Agent 来验证当前假设。

    流程:
    1. 如果有活跃的子 Agent (active_sub_agent_thread_id)，恢复它
    2. 否则创建新的子 Agent
    3. 执行子 Agent 图，流式桥接 SSE 事件
    4. 如果子 Agent hit interrupt，返回等待状态
    5. 如果子 Agent 完成，提取结果并返回
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="run_sub_agent", sid=sid)
    incident_id = state["incident_id"]

    hypotheses = state["hypotheses"]
    current_idx = state.get("current_hypothesis_index", 0)
    hypothesis = hypotheses[current_idx]
    results = list(state.get("hypothesis_results") or [])

    # 获取共享 checkpointer
    from src.main import get_checkpointer

    checkpointer = get_checkpointer()
    sub_graph = compile_investigation_graph(checkpointer=checkpointer)

    channel = EventPublisher.channel_for_incident(incident_id)
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())

    sub_thread_id = state.get("active_sub_agent_thread_id")
    is_resume = bool(sub_thread_id)

    if not is_resume:
        # 创建新的子 Agent
        sub_thread_id = str(uuid.uuid4())
        log.info(
            "Creating sub-agent",
            hypothesis=hypothesis["id"],
            thread_id=sub_thread_id,
        )

        prior_findings = _format_prior_findings(results)
        initial_prompt = (
            f"事件描述: {state['description']}\n\n"
            f"请验证假设 {hypothesis['id']}: {hypothesis['desc']}"
        )

        initial_state = {
            "messages": [HumanMessage(content=initial_prompt)],
            "incident_id": incident_id,
            "description": state["description"],
            "severity": state["severity"],
            "hypothesis_id": hypothesis["id"],
            "hypothesis_desc": hypothesis["desc"],
            "prior_findings": prior_findings,
            "kb_summary": state.get("kb_summary"),
            "is_complete": False,
            "needs_approval": False,
            "pending_tool_call": None,
            "approval_decision": None,
            "approval_supplement": None,
            "ask_human_count": 0,
            "tool_call_retry_count": 0,
        }

        config = {
            "configurable": {"thread_id": sub_thread_id},
            "recursion_limit": get_settings().agent_recursion_limit,
        }

        # 发布 sub_agent_started 事件
        try:
            await publisher.publish(
                channel,
                "sub_agent_started",
                {
                    "hypothesis_id": hypothesis["id"],
                    "hypothesis_desc": hypothesis["desc"],
                    "sub_agent_thread_id": sub_thread_id,
                    "phase": "investigation",
                },
            )
        except Exception as e:
            log.warning("Failed to publish sub_agent_started", error=str(e))

        # 执行子 Agent，桥接事件
        result = await _stream_sub_agent(
            sub_graph, initial_state, config, channel, publisher, hypothesis["id"], log
        )
    else:
        # 恢复已有的子 Agent
        log.info("Resuming sub-agent", hypothesis=hypothesis["id"], thread_id=sub_thread_id)

        config = {
            "configurable": {"thread_id": sub_thread_id},
            "recursion_limit": get_settings().agent_recursion_limit,
        }

        # 恢复子 Agent（通过 Command 传递审批/用户输入）
        result = await _resume_sub_agent(
            sub_graph, config, state, channel, publisher, hypothesis["id"], log
        )

    # 检查子 Agent 是否 hit interrupt
    if result["needs_interrupt"]:
        log.info(
            "Sub-agent hit interrupt",
            interrupt_type=result["interrupt_type"],
            hypothesis=hypothesis["id"],
        )
        return_state: dict = {
            "active_sub_agent_thread_id": sub_thread_id,
            "sub_agent_status": "waiting_for_human",
        }
        if result["interrupt_type"] == "human_approval":
            return_state["needs_approval"] = True
            return_state["pending_tool_call"] = result.get("pending_tool_call")
        return return_state

    # 子 Agent 完成
    log.info(
        "Sub-agent completed",
        hypothesis=hypothesis["id"],
        status=result.get("status", "inconclusive"),
    )

    # 提取调查结果
    finding = await _extract_findings(sub_graph, config, hypothesis)

    # 发布 sub_agent_completed 事件
    try:
        await publisher.publish(
            channel,
            "sub_agent_completed",
            {
                "hypothesis_id": hypothesis["id"],
                "status": finding["status"],
                "summary": finding["summary"][:500],
                "phase": "investigation",
            },
        )
    except Exception as e:
        log.warning("Failed to publish sub_agent_completed", error=str(e))

    results.append(finding)
    return {
        "hypothesis_results": results,
        "current_hypothesis_index": current_idx + 1,
        "active_sub_agent_thread_id": None,
        "sub_agent_status": "completed",
        "needs_approval": False,
        "pending_tool_call": None,
    }


async def _stream_sub_agent(
    sub_graph, initial_state, config, channel, publisher, hypothesis_id, log
) -> dict:
    """执行子 Agent 图，桥接 SSE 事件。返回执行结果。"""
    thinking_buffer = ""
    ask_human_active = False
    ask_human_streamed = False

    try:
        async for event in sub_graph.astream_events(initial_state, config=config, version="v2"):
            bridge_result = await _bridge_event(
                event, channel, publisher, hypothesis_id,
                thinking_buffer, ask_human_active, ask_human_streamed,
            )
            thinking_buffer = bridge_result["thinking_buffer"]
            ask_human_active = bridge_result["ask_human_active"]
            ask_human_streamed = bridge_result["ask_human_streamed"]
    except Exception as e:
        log.error("Sub-agent stream error", error=str(e))
        raise

    await publisher.flush_remaining(channel)

    # 检查子 Agent 是否 hit interrupt
    graph_state = await sub_graph.aget_state(config)
    next_nodes = graph_state.next or ()

    if "human_approval" in next_nodes:
        pending = _extract_sub_agent_pending_tool(graph_state.values)
        return {
            "needs_interrupt": True,
            "interrupt_type": "human_approval",
            "pending_tool_call": pending,
        }
    if "ask_human" in next_nodes:
        return {
            "needs_interrupt": True,
            "interrupt_type": "ask_human",
            "ask_human_streamed": ask_human_streamed,
        }

    return {"needs_interrupt": False}


async def _resume_sub_agent(sub_graph, config, coordinator_state, channel, publisher, hypothesis_id, log) -> dict:
    """恢复子 Agent（传递审批决定或用户输入）。"""
    from langgraph.types import Command

    graph_state = await sub_graph.aget_state(config)
    next_nodes = graph_state.next or ()
    thinking_buffer = ""
    ask_human_active = False
    ask_human_streamed = False

    if "human_approval" in next_nodes:
        # 传递审批决定
        decision = coordinator_state.get("approval_decision", "approved")
        supplement = coordinator_state.get("approval_supplement")
        state_update: dict = {"approval_decision": decision}
        if supplement:
            state_update["approval_supplement"] = supplement
        resume_input = Command(resume=None, update=state_update)
        log.info("Resuming sub-agent (approval)", decision=decision)
    elif "ask_human" in next_nodes:
        # 传递用户输入 —— 从 coordinator 最后一条消息获取
        last_msg = coordinator_state["messages"][-1]
        user_input = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        resume_input = Command(resume=user_input)
        log.info("Resuming sub-agent (human input)")
    else:
        log.warning("Sub-agent not at interrupt point", next_nodes=next_nodes)
        return {"needs_interrupt": False}

    try:
        async for event in sub_graph.astream_events(resume_input, config=config, version="v2"):
            bridge_result = await _bridge_event(
                event, channel, publisher, hypothesis_id,
                thinking_buffer, ask_human_active, ask_human_streamed,
            )
            thinking_buffer = bridge_result["thinking_buffer"]
            ask_human_active = bridge_result["ask_human_active"]
            ask_human_streamed = bridge_result["ask_human_streamed"]
    except Exception as e:
        log.error("Sub-agent resume stream error", error=str(e))
        raise

    await publisher.flush_remaining(channel)

    # 检查是否又 hit interrupt
    graph_state = await sub_graph.aget_state(config)
    next_nodes = graph_state.next or ()

    if "human_approval" in next_nodes:
        pending = _extract_sub_agent_pending_tool(graph_state.values)
        return {
            "needs_interrupt": True,
            "interrupt_type": "human_approval",
            "pending_tool_call": pending,
        }
    if "ask_human" in next_nodes:
        return {
            "needs_interrupt": True,
            "interrupt_type": "ask_human",
            "ask_human_streamed": ask_human_streamed,
        }

    return {"needs_interrupt": False}


async def _bridge_event(
    event, channel, publisher, hypothesis_id,
    thinking_buffer, ask_human_active, ask_human_streamed,
) -> dict:
    """桥接子 Agent 事件到 SSE channel，附加 sub_agent_id。"""
    kind = event.get("event")
    metadata = event.get("metadata", {})
    node = metadata.get("langgraph_node", "")

    # 跳过不需要桥接的节点
    if node in ("human_approval", "ask_human", "retry_tool_call"):
        return {
            "thinking_buffer": thinking_buffer,
            "ask_human_active": ask_human_active,
            "ask_human_streamed": ask_human_streamed,
        }

    if kind == "on_chat_model_stream":
        chunk = event["data"].get("chunk")
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
        if name in ("report_findings", "ask_human"):
            pass  # 不桥接这些工具的 SSE
        else:
            run_id = event.get("run_id", "")
            await publisher.publish(
                channel,
                "tool_use",
                {
                    "name": name,
                    "args": event["data"].get("input", {}),
                    "tool_call_id": run_id,
                    "phase": "investigation",
                    "sub_agent_id": hypothesis_id,
                },
            )

    elif kind == "on_tool_end":
        name = event.get("name", "")
        if name in ("report_findings", "ask_human"):
            pass
        elif name == "read_skill":
            args = event["data"].get("input", {})
            output = str(event["data"].get("output", ""))
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
            output_str = str(event["data"].get("output", ""))
            await publisher.publish(
                channel,
                "tool_result",
                {
                    "name": name,
                    "output": output_str,
                    "tool_call_id": run_id,
                    "phase": "investigation",
                    "sub_agent_id": hypothesis_id,
                },
            )

    return {
        "thinking_buffer": thinking_buffer,
        "ask_human_active": ask_human_active,
        "ask_human_streamed": ask_human_streamed,
    }


def _extract_sub_agent_pending_tool(vals: dict) -> dict | None:
    """从子 Agent 状态中提取待审批的工具调用。"""
    _APPROVAL_TOOLS = {"ssh_bash", "bash", "service_exec"}
    messages = vals.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] in _APPROVAL_TOOLS:
                    return tc
    return None


async def _extract_findings(sub_graph, config, hypothesis) -> HypothesisResult:
    """从子 Agent 最终状态中提取调查结果。"""
    graph_state = await sub_graph.aget_state(config)
    vals = graph_state.values
    messages = vals.get("messages", [])

    # 从最后的 report_findings tool_call 中提取
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "report_findings":
                    args = tc.get("args", {})
                    return HypothesisResult(
                        hypothesis_id=hypothesis["id"],
                        hypothesis_desc=hypothesis["desc"],
                        status=args.get("status", "inconclusive"),
                        summary=args.get("summary", ""),
                        evidence=args.get("evidence", ""),
                    )
            break

    # Fallback: 没有 report_findings（可能被强制结束）
    return HypothesisResult(
        hypothesis_id=hypothesis["id"],
        hypothesis_desc=hypothesis["desc"],
        status="inconclusive",
        summary="调查未能得出结论",
        evidence="",
    )
