"""只读工具 —— skill_read, list_servers, list_services。"""

from langchain_core.tools import StructuredTool

from src.ops_agent.tools.base_tool import BaseTool, PermissionBehavior, PermissionResult
from src.ops_agent.tools.truncation import truncate_output


class SkillReadTool(BaseTool):
    """读取技能文件。"""

    @property
    def name(self) -> str:
        return "skill_read"

    @property
    def summary(self) -> str:
        return "读取技能文件"

    @property
    def prompt(self) -> str:
        return """\
读取技能仓库中的文件，获取标准化运维操作指南。

## 参数
- path（必填）：技能路径
  - "?" — 列出所有可用技能
  - "slug" — 读取该技能的 SKILL.md（概述和步骤）
  - "slug/scripts/x.sh" — 读取具体脚本文件

## 使用原则
- 先用 "?" 查看可用技能列表
- 找到匹配技能后先读 SKILL.md 了解整体流程
- 按需加载具体脚本，不要一次性读取所有文件
- 不要复制粘贴大段技能内容，总结关键步骤即可"""

    def is_read_only(self, **kw) -> bool:
        return True

    def is_concurrency_safe(self, **kw) -> bool:
        return True

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    def _read_sync(self, path: str) -> str:
        """同步读取技能文件（SkillService 是同步的）。"""
        from src.services.skill_service import SkillService

        service = SkillService()
        if path.strip() == "?":
            available = service.get_available_skills()
            if not available:
                return "当前没有可用技能。"
            lines = ["所有可用技能:"]
            for s in available:
                lines.append(f"- {s['slug']}: {s['description']}")
            return "\n".join(lines)
        parts = path.split("/", 1)
        slug = parts[0]
        rel_path = parts[1] if len(parts) > 1 else None
        try:
            return service.read_file(slug, rel_path)
        except FileNotFoundError:
            return f"未找到: {path}"

    async def execute(self, **kw) -> str:
        return self._read_sync(kw.get("path", "?"))

    def _build_langchain_tool(self):
        tool_self = self

        def _execute(path: str) -> str:
            result = tool_self._read_sync(path)
            return truncate_output(result, tool_self.max_result_size_chars)

        return StructuredTool.from_function(
            func=_execute,
            name=self.name,
            description=self.prompt,
        )


class ListServersTool(BaseTool):
    """列出所有可用服务器。"""

    @property
    def name(self) -> str:
        return "list_servers"

    @property
    def summary(self) -> str:
        return "列出所有可用服务器"

    @property
    def prompt(self) -> str:
        return """\
列出所有已注册的可用服务器，返回 id, name, host, status。

## 使用原则
- 在使用 ssh_bash 前必须先调用此工具获取有效的 server_id（UUID 格式）
- 返回的 id 是 UUID，不是主机名，不要自行构造
- 只返回非 offline 状态的服务器"""

    def is_read_only(self, **kw) -> bool:
        return True

    def is_concurrency_safe(self, **kw) -> bool:
        return True

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> list[dict] | str:
        from src.ops_agent.tools.ssh_bash_tool import list_servers

        result = await list_servers()
        if not result:
            return "当前没有注册任何服务器。"
        return result

    def _build_langchain_tool(self):
        tool_self = self

        async def _execute() -> list[dict] | str:
            return await tool_self.execute()

        return StructuredTool.from_function(
            coroutine=_execute,
            name=self.name,
            description=self.prompt,
        )


class ListServicesTool(BaseTool):
    """列出所有可用服务。"""

    @property
    def name(self) -> str:
        return "list_services"

    @property
    def summary(self) -> str:
        return "列出所有可用服务"

    @property
    def prompt(self) -> str:
        return """\
列出所有已注册的可用服务，返回 id, name, service_type, host, port, database, status。

## 使用原则
- 在使用 service_exec 前必须先调用此工具获取有效的 service_id（UUID 格式）
- 返回的 service_type 决定了 service_exec 中应使用的命令语法
- 只返回非 offline 状态的服务"""

    def is_read_only(self, **kw) -> bool:
        return True

    def is_concurrency_safe(self, **kw) -> bool:
        return True

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> list[dict] | str:
        from src.ops_agent.tools.service_exec_tool import list_services

        result = await list_services()
        if not result:
            return "当前没有注册任何服务。"
        return result

    def _build_langchain_tool(self):
        tool_self = self

        async def _execute() -> list[dict] | str:
            return await tool_self.execute()

        return StructuredTool.from_function(
            coroutine=_execute,
            name=self.name,
            description=self.prompt,
        )
