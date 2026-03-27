"""子 Agent 生命周期管理节点 —— 创建/恢复子 Agent，桥接 SSE 事件。"""

import uuid

import orjson
from langchain_core.messages import HumanMessage, ToolMessage

from src.db.connection import get_session_factory
from src.env import get_settings
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.ops_agent.event_publisher import EventPublisher
from src.ops_agent.investigation_graph import compile_investigation_graph
from src.ops_agent.state import CoordinatorState, HypothesisResult
from src.ops_agent.tools.tool_classifier import ShellSafety, ServiceSafety, CommandType
from src.services.approval_service import ApprovalService
from src.services.notification_service import notify_fire_and_forget


def _format_prior_findings(results: list[HypothesisResult]) -> str:
    """将之前子 Agent 的调查结果格式化为上下文。"""
    if not results:
        return ""
    lines = []
    for r in results:
        status_map = {"confirmed": "已确认", "eliminated": "已排除", "inconclusive": "证据不足"}
        status_zh = status_map.get(r["status"], r["status"])
        line = f"- {r['hypothesis_id']} [{status_zh}] {r['hypothesis_desc']}: {r['summary']}"
        action = r.get("action_taken", "")
        if action:
            line += f" [已修复: {action}]"
        lines.append(line)
    return "\n".join(lines)


def _extract_launch_info(state: CoordinatorState) -> tuple[str, str, str]:
    """从最近的 launch_investigation tool_call 中提取假设信息和 tool_call_id。"""
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"] == "launch_investigation":
                    args = tc.get("args", {})
                    return (
                        args.get("hypothesis_id", "H1"),
                        args.get("hypothesis_desc", ""),
                        tc["id"],
                    )
            break
    return "H1", "", ""


async def _create_and_publish_approval(
    publisher: EventPublisher,
    channel: str,
    pending_tool_call: dict | None,
    incident_id: str,
    description: str,
    severity: str,
    hypothesis_id: str,
    log,
) -> str:
    """在子 Agent 上下文中创建 ApprovalRequest 并发布 approval_required 事件。

    返回 approval_id 字符串。
    """
    if not pending_tool_call:
        return ""

    args = pending_tool_call.get("args", {})
    tool_name = pending_tool_call["name"]
    command = args.get("command", "")

    # 风险分类
    if tool_name in ("ssh_bash", "bash"):
        cmd_type = ShellSafety.classify(command, local=(tool_name == "bash"))
    elif tool_name == "service_exec":
        from src.ops_agent.nodes.investigation_agent import _get_service_type

        service_type = await _get_service_type(args.get("service_id", ""))
        cmd_type = ServiceSafety.classify(service_type, command)
    else:
        cmd_type = CommandType.WRITE

    risk_level = "HIGH" if cmd_type == CommandType.DANGEROUS else "MEDIUM"
    log.info(
        "Creating sub-agent approval",
        tool=tool_name,
        cmd_type=cmd_type.name,
        risk=risk_level,
        hypothesis=hypothesis_id,
    )

    # 创建 DB 记录
    async with get_session_factory()() as session:
        approval = await ApprovalService(session).create(
            incident_id=uuid.UUID(incident_id),
            tool_name=tool_name,
            tool_args=orjson.dumps(args).decode(),
            risk_level=risk_level,
            explanation=args.get("explanation"),
        )
    approval_id = str(approval.id)
    log.info("Approval created", approval_id=approval_id)

    # 发布 approval_required 事件（带 sub_agent_id）
    await publisher.publish(
        channel,
        "approval_required",
        {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "tool_args": {**args, "risk_level": risk_level},
            "tool_call_id": pending_tool_call.get("id", ""),
            "sub_agent_id": hypothesis_id,
            "phase": "investigation",
        },
    )

    # 通知
    notify_fire_and_forget(
        "need_approval",
        incident_id,
        description[:80],
        severity=severity,
        command=command,
        risk_level=risk_level,
        explanation=args.get("explanation", ""),
    )

    return approval_id


async def run_sub_agent_node(state: CoordinatorState) -> dict:
    """创建或恢复子 Agent 来验证当前假设。

    由 coordinator_agent 调用 launch_investigation 后触发。
    完成后返回 ToolMessage 给 coordinator_agent。
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="run_sub_agent", sid=sid)
    incident_id = state["incident_id"]
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
        # 从 launch_investigation tool_call 中提取假设信息
        hypothesis_id, hypothesis_desc, launch_tool_call_id = _extract_launch_info(state)
        hypothesis = {"id": hypothesis_id, "desc": hypothesis_desc}

        sub_thread_id = str(uuid.uuid4())
        log.info("Creating sub-agent", hypothesis=hypothesis_id, thread_id=sub_thread_id)

        prior_findings = _format_prior_findings(results)
        initial_prompt = (
            f"事件描述: {state['description']}\n\n"
            f"请验证假设 {hypothesis_id}: {hypothesis_desc}"
        )

        initial_state = {
            "messages": [HumanMessage(content=initial_prompt)],
            "incident_id": incident_id,
            "description": state["description"],
            "severity": state["severity"],
            "hypothesis_id": hypothesis_id,
            "hypothesis_desc": hypothesis_desc,
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
                    "hypothesis_id": hypothesis_id,
                    "hypothesis_desc": hypothesis_desc,
                    "sub_agent_thread_id": sub_thread_id,
                    "phase": "investigation",
                },
            )
        except Exception as e:
            log.warning("Failed to publish sub_agent_started", error=str(e))

        # 执行子 Agent，桥接事件
        result = await _stream_sub_agent(
            sub_graph, initial_state, config, channel, publisher, hypothesis_id, log
        )
    else:
        # 恢复已有的子 Agent
        hypothesis_id = state.get("active_hypothesis_id", "H1")
        hypothesis_desc = state.get("active_hypothesis_desc", "")
        launch_tool_call_id = state.get("pending_launch_tool_call_id", "")
        hypothesis = {"id": hypothesis_id, "desc": hypothesis_desc}

        log.info("Resuming sub-agent", hypothesis=hypothesis_id, thread_id=sub_thread_id)

        config = {
            "configurable": {"thread_id": sub_thread_id},
            "recursion_limit": get_settings().agent_recursion_limit,
        }

        # 传递 approval_id 用于标记 resume 后的 tool_use 事件
        approval_id_for_resume = ""
        if state.get("approval_decision") == "approved" and state.get("pending_approval_id"):
            approval_id_for_resume = state["pending_approval_id"]

        result = await _resume_sub_agent(
            sub_graph, config, state, channel, publisher, hypothesis_id, log,
            approval_id=approval_id_for_resume,
        )

    # 子 Agent hit interrupt → 创建审批/通知，返回等待状态
    if result["needs_interrupt"]:
        log.info(
            "Sub-agent hit interrupt",
            interrupt_type=result["interrupt_type"],
            hypothesis=hypothesis["id"],
        )
        return_state: dict = {
            "active_sub_agent_thread_id": sub_thread_id,
            "active_hypothesis_id": hypothesis["id"],
            "active_hypothesis_desc": hypothesis["desc"],
            "pending_launch_tool_call_id": launch_tool_call_id,
            "sub_agent_status": "waiting_for_human",
        }
        if result["interrupt_type"] == "human_approval":
            pending = result.get("pending_tool_call")
            approval_id = await _create_and_publish_approval(
                publisher, channel, pending,
                incident_id, state["description"], state["severity"],
                hypothesis["id"], log,
            )
            return_state["needs_approval"] = True
            return_state["pending_tool_call"] = pending
            return_state["pending_approval_id"] = approval_id
        elif result["interrupt_type"] == "ask_human":
            # ask_human 通知
            notify_fire_and_forget(
                "ask_human",
                incident_id,
                state.get("description", "")[:80],
                severity=state.get("severity", ""),
                question="（子 Agent 提问）",
            )
        return return_state

    # 子 Agent 完成 → 提取结果，构造 ToolMessage 返回给 coordinator
    finding = await _extract_findings(sub_graph, config, hypothesis)
    log.info("Sub-agent completed", hypothesis=hypothesis["id"], status=finding["status"])

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

    # 构造 ToolMessage 返回给 coordinator_agent
    status_zh = {"confirmed": "已确认", "eliminated": "已排除", "inconclusive": "证据不足"}
    action_taken = finding.get("action_taken", "")
    tool_message_content = (
        f"假设 {finding['hypothesis_id']} 调查完成。\n"
        f"状态: {status_zh.get(finding['status'], finding['status'])}\n"
        f"摘要: {finding['summary']}\n"
        f"证据: {finding['evidence']}"
    )
    if action_taken:
        tool_message_content += f"\n已执行修复: {action_taken}"

    results.append(finding)
    return {
        "messages": [ToolMessage(content=tool_message_content, tool_call_id=launch_tool_call_id)],
        "hypothesis_results": results,
        "active_sub_agent_thread_id": None,
        "active_hypothesis_id": None,
        "active_hypothesis_desc": None,
        "pending_launch_tool_call_id": None,
        "sub_agent_status": "completed",
        "needs_approval": False,
        "pending_tool_call": None,
        "pending_approval_id": None,
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


async def _resume_sub_agent(
    sub_graph, config, coordinator_state, channel, publisher, hypothesis_id, log,
    approval_id: str = "",
) -> dict:
    """恢复子 Agent（传递审批决定或用户输入）。"""
    from langgraph.types import Command

    graph_state = await sub_graph.aget_state(config)
    next_nodes = graph_state.next or ()
    thinking_buffer = ""
    ask_human_active = False
    ask_human_streamed = False

    # 确定 approval_tool_name 用于标记 resume 后的 tool_use 事件
    approval_tool_name = ""
    if "human_approval" in next_nodes:
        decision = coordinator_state.get("approval_decision", "approved")
        supplement = coordinator_state.get("approval_supplement")
        state_update: dict = {"approval_decision": decision}
        if supplement:
            state_update["approval_supplement"] = supplement
        resume_input = Command(resume=None, update=state_update)
        log.info("Resuming sub-agent (approval)", decision=decision)
        # 仅在 approved 时传递 approval_id 标记
        if decision == "approved" and approval_id:
            pending = _extract_sub_agent_pending_tool(graph_state.values)
            if pending:
                approval_tool_name = pending["name"]
    elif "ask_human" in next_nodes:
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
                approval_id=approval_id, approval_tool_name=approval_tool_name,
            )
            thinking_buffer = bridge_result["thinking_buffer"]
            ask_human_active = bridge_result["ask_human_active"]
            ask_human_streamed = bridge_result["ask_human_streamed"]
            # approval_id 标记仅用于第一个匹配的 tool_use/tool_result
            approval_id = bridge_result.get("approval_id", approval_id)
            approval_tool_name = bridge_result.get("approval_tool_name", approval_tool_name)
    except Exception as e:
        log.error("Sub-agent resume stream error", error=str(e))
        raise

    await publisher.flush_remaining(channel)

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
    approval_id: str = "", approval_tool_name: str = "",
) -> dict:
    """桥接子 Agent 事件到 SSE channel，附加 sub_agent_id。"""
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
        if name in ("report_findings", "ask_human", "read_skill"):
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
            output_raw = event["data"].get("output", "")
            output_str = str(output_raw)
            status = "success"
            if isinstance(output_raw, dict):
                if output_raw.get("exit_code") not in (None, 0):
                    status = "error"
                elif output_raw.get("error"):
                    status = "error"
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

    return {
        "thinking_buffer": thinking_buffer,
        "ask_human_active": ask_human_active,
        "ask_human_streamed": ask_human_streamed,
        "approval_id": approval_id,
        "approval_tool_name": approval_tool_name,
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
                        action_taken=args.get("action_taken", ""),
                    )
            break

    return HypothesisResult(
        hypothesis_id=hypothesis["id"],
        hypothesis_desc=hypothesis["desc"],
        status="inconclusive",
        summary="调查未能得出结论",
        evidence="",
        action_taken="",
    )
