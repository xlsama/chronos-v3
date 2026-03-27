"""假设调度节点 —— 从 planner 输出解析假设，决定下一步。"""

import re

from src.lib.logger import get_logger
from src.ops_agent.state import CoordinatorState


def _parse_hypotheses_from_plan(plan_md: str) -> list[dict]:
    """从 planner 输出的 Markdown 中解析假设列表。

    格式: ### H{n} [待验证] 假设描述
    """
    if not plan_md:
        return []

    matches = re.findall(
        r"###\s+(H\d+)\s+\[(?:待验证|pending)\]\s+(.+?)(?:\n|$)",
        plan_md,
    )
    hypotheses = []
    for i, (h_id, desc) in enumerate(matches):
        hypotheses.append({
            "id": h_id,
            "desc": desc.strip(),
            "priority": i + 1,
        })
    return hypotheses


async def hypothesis_router_node(state: CoordinatorState) -> dict:
    """假设调度节点。

    首次进入时从 plan_md 解析假设列表并初始化。
    后续进入时检查当前假设结果，决定下一步。
    """
    sid = state["incident_id"][:8]
    log = get_logger(component="hypothesis_router", sid=sid)

    hypotheses = state.get("hypotheses") or []
    results = state.get("hypothesis_results") or []
    current_idx = state.get("current_hypothesis_index", 0)

    # 首次进入：从 plan_md 解析假设
    if not hypotheses:
        from src.ops_agent.nodes.main_agent import _read_plan_from_db

        plan_md = await _read_plan_from_db(state["incident_id"])
        hypotheses = _parse_hypotheses_from_plan(plan_md)
        if not hypotheses:
            log.warning("No hypotheses found in plan, using fallback")
            hypotheses = [{"id": "H1", "desc": "通用排查", "priority": 1}]
        log.info("Parsed hypotheses", count=len(hypotheses), hypotheses=hypotheses)
        return {
            "hypotheses": hypotheses,
            "current_hypothesis_index": 0,
            "hypothesis_results": [],
        }

    # 检查上一个假设的结果
    if results:
        last_result = results[-1]
        log.info(
            "Last hypothesis result",
            hypothesis=last_result["hypothesis_id"],
            status=last_result["status"],
        )
        # 如果上一个假设已确认，直接进入 synthesize
        if last_result["status"] == "confirmed":
            log.info("Hypothesis confirmed, routing to synthesize")
            return {}

    # 检查是否还有未验证的假设
    if current_idx < len(hypotheses):
        log.info(
            "Next hypothesis",
            hypothesis=hypotheses[current_idx]["id"],
            desc=hypotheses[current_idx]["desc"],
        )
        return {}

    # 所有假设都已验证完毕
    log.info("All hypotheses exhausted, routing to synthesize")
    return {}


def route_after_hypothesis(state: CoordinatorState) -> str:
    """hypothesis_router 之后的路由。"""
    log = get_logger(component="hypothesis_router", sid=state["incident_id"][:8])

    hypotheses = state.get("hypotheses") or []
    results = state.get("hypothesis_results") or []
    current_idx = state.get("current_hypothesis_index", 0)

    # 子 Agent 处于等待人工输入状态，路由回 run_sub_agent 恢复
    sub_status = state.get("sub_agent_status")
    if sub_status == "waiting_for_human":
        if state.get("needs_approval"):
            log.info("-> sub_agent_approval (resume sub-agent)")
            return "sub_agent_approval"
        log.info("-> sub_agent_ask_human (resume sub-agent)")
        return "sub_agent_ask_human"

    # 有假设被确认 → synthesize
    if results and results[-1]["status"] == "confirmed":
        log.info("-> synthesize (hypothesis confirmed)")
        return "synthesize"

    # 还有未验证的假设 → run_sub_agent
    if current_idx < len(hypotheses):
        log.info("-> run_sub_agent", hypothesis=hypotheses[current_idx]["id"])
        return "run_sub_agent"

    # 所有假设都已验证 → synthesize
    log.info("-> synthesize (all hypotheses exhausted)")
    return "synthesize"
