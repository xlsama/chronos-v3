"""协调工具 —— launch_investigation, update_plan, complete, ask_human, conclude。"""

from __future__ import annotations

import uuid
from typing import Annotated

from langchain_core.tools import StructuredTool, tool
from langgraph.prebuilt import InjectedState

from src.ops_agent.tools.base_tool import BaseTool, PermissionBehavior, PermissionResult


class LaunchInvestigationTool(BaseTool):
    """启动子 Agent 验证假设。"""

    @property
    def name(self) -> str:
        return "launch_investigation"

    @property
    def summary(self) -> str:
        return "启动子 Agent 验证假设"

    @property
    def prompt(self) -> str:
        return """\
启动一个子 Agent 来验证指定假设。子 Agent 独立执行排查（SSH 命令、数据库查询等），完成后返回调查结果。

## 参数
- hypothesis_id（必填）：假设编号，如 "H1"，必须与调查计划中的编号对应
- hypothesis_title（必填）：假设短标题（15字以内），如"数据库连接池耗尽"、"查询条件过滤异常"
- hypothesis_desc（必填）：假设详细描述，包含具体排查方向和步骤

## 使用原则
- 每次只启动一个子 Agent，等完成再决定下一步
- 如果有匹配的技能（skill），在 hypothesis_desc 中提示子 Agent 参考
- 子 Agent 确认问题后可直接执行修复操作"""

    def is_read_only(self, **kw) -> bool:
        return False

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> str:
        hid = kw.get("hypothesis_id", "H1")
        title = kw.get("hypothesis_title", "")
        return f"子 Agent 已启动，正在验证假设 {hid}: {title}"

    def _build_langchain_tool(self):
        def _execute(hypothesis_id: str, hypothesis_title: str, hypothesis_desc: str) -> str:
            return f"子 Agent 已启动，正在验证假设 {hypothesis_id}: {hypothesis_title}"

        return StructuredTool.from_function(
            func=_execute,
            name=self.name,
            description=self.prompt,
        )


class UpdatePlanTool(BaseTool):
    """更新调查计划。"""

    @property
    def name(self) -> str:
        return "update_plan"

    @property
    def summary(self) -> str:
        return "更新调查计划"

    @property
    def prompt(self) -> str:
        return """\
更新调查计划。收到子 Agent 结果后，更新假设状态和证据。

## 参数
- plan_md（必填）：更新后的完整调查计划（Markdown 格式），会替换当前计划

## 使用原则
- 每次收到子 Agent 结果后必须调用，再决定下一步
- 将假设状态从 [待验证]/[排查中] 更新为 [已确认] 或 [已排除]
- 记录关键证据和发现
- 如果所有假设已排除，添加新假设继续排查"""

    def is_read_only(self, **kw) -> bool:
        return False

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> str:
        from src.db.connection import get_session_factory
        from src.db.models import Incident
        from src.lib.logger import get_logger
        from src.lib.redis import get_redis
        from src.ops_agent.event_publisher import EventPublisher

        plan_md = kw.get("plan_md", "")
        state = kw.get("state", {})
        incident_id = state.get("incident_id", "") if isinstance(state, dict) else ""
        log = get_logger(component="update_plan")

        try:
            async with get_session_factory()() as session:
                incident = await session.get(Incident, uuid.UUID(incident_id))
                if incident:
                    incident.plan_md = plan_md
                    await session.commit()
        except Exception as e:
            log.warning("Failed to save plan to DB", error=str(e))

        try:
            channel = EventPublisher.channel_for_incident(incident_id)
            publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
            await publisher.publish(
                channel, "plan_updated", {"plan_md": plan_md, "phase": "investigation"}
            )
        except Exception as e:
            log.warning("Failed to publish plan_updated event", error=str(e))

        return "调查计划已更新"

    def _build_langchain_tool(self):
        tool_self = self
        _prompt = self.prompt

        @tool(description=_prompt)
        async def update_plan(
            plan_md: str,
            state: Annotated[dict, InjectedState],
        ) -> str:
            """更新调查计划。"""
            return await tool_self.execute(plan_md=plan_md, state=state)

        return update_plan


class CompleteTool(BaseTool):
    """排查完成，输出最终结论。"""

    @property
    def name(self) -> str:
        return "complete"

    @property
    def summary(self) -> str:
        return "排查完成，输出最终结论"

    @property
    def prompt(self) -> str:
        return """\
排查完成，输出最终结论。

## 参数
- answer_md（必填）：完整的排查报告（Markdown），包含根因、证据链、处置过程、优化建议

## 使用原则
- 只在所有排查完成、问题已解决或已充分诊断后调用
- 对于非故障类问题（问候/闲聊/简单查询），直接给出简短回复即可
- 报告应包含：根因分析、关键证据、修复操作及验证结果、长期优化建议"""

    def is_read_only(self, **kw) -> bool:
        return False

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> str:
        return kw.get("answer_md", "")

    def _build_langchain_tool(self):
        def _execute(answer_md: str) -> str:
            return answer_md

        return StructuredTool.from_function(
            func=_execute,
            name=self.name,
            description=self.prompt,
        )


class AskHumanTool(BaseTool):
    """向用户提问。"""

    @property
    def name(self) -> str:
        return "ask_human"

    @property
    def summary(self) -> str:
        return "向用户提问获取关键信息"

    @property
    def prompt(self) -> str:
        return """\
当缺少关键信息无法继续排查时，向用户提问。

## 参数
- question（必填）：简短精练的问题（1-3行），只写需要用户回答的关键问题

## 使用原则
- 分析推理直接写在回复中，不要放进 question
- 不要追问系统中不存在的资源（如未注册的服务器）
- 谨慎使用，每次会话最多 5 次
- 只在真正缺少信息时使用，不用于确认或汇报"""

    def is_read_only(self, **kw) -> bool:
        return True

    def is_concurrency_safe(self, **kw) -> bool:
        return False  # 需要中断图执行

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> str:
        return kw.get("question", "")

    def _build_langchain_tool(self):
        def _execute(question: str) -> str:
            return question

        return StructuredTool.from_function(
            func=_execute,
            name=self.name,
            description=self.prompt,
        )


class ConcludeTool(BaseTool):
    """子 Agent 调查完成后提交结论。"""

    @property
    def name(self) -> str:
        return "conclude"

    @property
    def summary(self) -> str:
        return "子 Agent 提交调查结论"

    @property
    def prompt(self) -> str:
        return """\
调查完成后调用，提交本次调查的结论与结果。仅子 Agent 使用。

## 参数
- status（必填）："confirmed"（假设成立）/ "eliminated"（假设排除）/ "inconclusive"（证据不足）
- summary（必填）：一句话结论摘要
- detail（必填）：结构化排查报告（Markdown），包含以下章节：
  - ## 结论 — 假设是否成立及核心发现
  - ## 排查链路 — 关键步骤：`命令` → 发现（只保留有价值的步骤）
  - ## 根因 — 根本原因 + 关键证据
  - ## 修复操作 — 执行的命令 + 验证结果（或"无需修复"）"""

    def is_read_only(self, **kw) -> bool:
        return False

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> str:
        status = kw.get("status", "inconclusive")
        summary = kw.get("summary", "")
        return f"调查结果已记录: status={status}, summary={summary}"

    def _build_langchain_tool(self):
        def _execute(status: str, summary: str, detail: str) -> str:
            return f"调查结果已记录: status={status}, summary={summary}"

        return StructuredTool.from_function(
            func=_execute,
            name=self.name,
            description=self.prompt,
        )
