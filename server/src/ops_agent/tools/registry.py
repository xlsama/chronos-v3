"""统一 Tool Registry —— 所有 Agent 工具的注册中心。

提供:
- get_tool(name): 获取工具实例（用于路由权限检查、审批分类）
- build_tools_for_agent(agent_type): 按 Agent 类型返回 LangChain 工具列表
- build_tool_guide_for_agent(agent_type): 返回 Agent 级别的工具使用原则
- APPROVAL_TOOL_NAMES: 可能需要审批的工具名集合
"""

from __future__ import annotations

from src.ops_agent.tools.base_tool import BaseTool

# 可能需要审批的工具名集合（check_permissions 可能返回 ASK）
APPROVAL_TOOL_NAMES = frozenset({"ssh_bash", "bash", "service_exec"})

# Agent 类型 → 工具名列表
_AGENT_TOOL_MAP = {
    "main": [
        "spawn_agent",
        "spawn_parallel_agents",
        "spawn_verification",
        "update_plan",
        "skill_read",
        "list_servers",
        "list_services",
        "complete",
        "ask_human",
    ],
    "investigation": [
        "ssh_bash",
        "bash",
        "service_exec",
        "skill_read",
        "list_servers",
        "list_services",
        "ask_human",
        "conclude",
    ],
    "verification": [
        "ssh_bash",
        "bash",
        "service_exec",
        "skill_read",
        "list_servers",
        "list_services",
        "ask_human",
        "submit_verification",
    ],
    "plan": [
        "skill_read",
        "list_servers",
        "list_services",
    ],
}

# Agent 级别的工具使用原则（注入 system prompt，不重复工具本身的说明）
_AGENT_TOOL_GUIDE = {
    "main": """\
## 工具使用原则

- 不直接执行排查命令（ssh_bash/bash/service_exec），由子 Agent 负责
- 多个独立假设可并行验证时，用 spawn_parallel_agents 同时启动（最多 3 个）
- 假设有先后依赖时，用 spawn_agent 逐个执行
- 收到子 Agent 结果后先 update_plan，再决定下一步
- 历史事件是线索不是答案：相同症状可能不同根因
- 信息不足时 ask_human，不追问系统中不存在的资源
- 有匹配技能时在 hypothesis_desc 中提示子 Agent 参考""",
    "investigation": """\
## 工具使用原则

- 先只读命令收集证据，再考虑写操作修复
- 权限不足加 sudo 重试
- 不要用 2>/dev/null 吞错误
- 优先检查 Docker 容器状态和日志
- 进程存活 ≠ 服务正常：接口超时时用 service_exec 检查依赖服务
- 能修的就修（重启/扩容等低风险操作），修完要验证
- 写操作在 explanation 中说明原因和风险""",
    "verification": """\
## 工具使用原则

- 你是验证者，不是修复者 — 只验证结论是否正确，不做修复操作
- 每项验证必须执行实际命令，禁止"看起来没问题"式的纯推理验证
- 可自验证的优先自验证（curl、ps、tail 等）
- 无法自验证时用 ask_human 请用户确认
- 无权限/服务不可达时标记 SKIPPED 并说明原因
- 写操作在 explanation 中说明原因和风险""",
    "plan": "",
}


# ═══════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════

_ALL_TOOLS: dict[str, BaseTool] | None = None


def _ensure_registered() -> dict[str, BaseTool]:
    global _ALL_TOOLS
    if _ALL_TOOLS is not None:
        return _ALL_TOOLS

    # Lazy import 避免循环依赖
    from src.ops_agent.tools.bash_tool import BashTool
    from src.ops_agent.tools.coordination_tools import (
        AskHumanTool,
        CompleteTool,
        ConcludeTool,
        SpawnAgentTool,
        SpawnParallelAgentsTool,
        SpawnVerificationTool,
        SubmitVerificationTool,
        UpdatePlanTool,
    )
    from src.ops_agent.tools.readonly_tools import (
        ListServersTool,
        ListServicesTool,
        SkillReadTool,
    )
    from src.ops_agent.tools.service_exec_tool import ServiceExecTool
    from src.ops_agent.tools.ssh_bash_tool import SSHBashTool

    instances: list[BaseTool] = [
        # 执行工具
        BashTool(),
        SSHBashTool(),
        ServiceExecTool(),
        # 共享只读工具
        SkillReadTool(),
        ListServersTool(),
        ListServicesTool(),
        # 协调工具
        SpawnAgentTool(),
        SpawnParallelAgentsTool(),
        SpawnVerificationTool(),
        UpdatePlanTool(),
        CompleteTool(),
        AskHumanTool(),
        ConcludeTool(),
        SubmitVerificationTool(),
    ]

    _ALL_TOOLS = {t.name: t for t in instances}
    return _ALL_TOOLS


def get_tool(name: str) -> BaseTool | None:
    """获取工具实例。"""
    return _ensure_registered().get(name)


def get_all_tools() -> dict[str, BaseTool]:
    """获取所有工具实例。"""
    return _ensure_registered()


def build_tools_for_agent(agent_type: str) -> list:
    """按 Agent 类型返回 LangChain 工具列表。"""
    registry = _ensure_registered()
    names = _AGENT_TOOL_MAP.get(agent_type)
    if names is None:
        raise ValueError(f"Unknown agent type: {agent_type}")
    return [registry[n].to_langchain_tool() for n in names]


def build_tool_guide_for_agent(agent_type: str) -> str:
    """返回 Agent 级别的工具使用原则（注入 system prompt）。

    这不是工具本身的说明（那在 tool definition 中），
    而是该 Agent 如何协调使用这些工具的原则。
    """
    return _AGENT_TOOL_GUIDE.get(agent_type, "")
