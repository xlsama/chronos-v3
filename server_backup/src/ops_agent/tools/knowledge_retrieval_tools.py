"""按需知识检索工具 —— search_knowledge, search_incidents。

供主 Agent、Investigation Agent、Plan Agent 在排查过程中按需检索知识库和历史故障。
与 gather_context 阶段的预加载互补：gather_context 提供初始上下文，
这些工具允许排查过程中发现新线索时追加检索。
"""

from langchain_core.tools import StructuredTool

from src.ops_agent.tools.base_tool import BaseTool, PermissionBehavior, PermissionResult
from src.ops_agent.tools.truncation import truncate_output


class SearchKnowledgeTool(BaseTool):
    """按需搜索项目知识库。"""

    @property
    def name(self) -> str:
        return "search_knowledge"

    @property
    def summary(self) -> str:
        return "搜索项目知识库"

    @property
    def prompt(self) -> str:
        return """\
搜索项目知识库，获取架构文档、部署信息、服务拓扑、API 文档、运维手册等。

## 参数
- query（必填）：搜索查询，描述你需要查找的信息

## 适用场景
- 需要了解某个服务的架构、部署方式、依赖关系
- 查找特定接口的文档、配置说明
- 排查中发现新的服务/组件名称，需要补充背景知识
- 验证假设时需要参考服务拓扑或数据链路文档

## 使用原则
- gather_context 阶段已提供初始知识库上下文，仅在需要补充信息时使用
- query 应具体——用服务名、组件名、错误关键词，避免泛泛搜索
- 返回结果按相关性排序，低相关结果已自动过滤"""

    def is_read_only(self, **kw) -> bool:
        return True

    def is_concurrency_safe(self, **kw) -> bool:
        return True

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> str:
        from src.ops_agent.tools.knowledge_tools import search_knowledge_base

        query = kw.get("query", "")
        text, _ = await search_knowledge_base(query=query)
        return text

    def _build_langchain_tool(self):
        tool_self = self

        async def _execute(query: str) -> str:
            result = await tool_self.execute(query=query)
            return truncate_output(result, tool_self.max_result_size_chars)

        return StructuredTool.from_function(
            coroutine=_execute,
            name=self.name,
            description=self.prompt,
        )


class SearchIncidentsTool(BaseTool):
    """按需搜索历史故障记录。"""

    @property
    def name(self) -> str:
        return "search_incidents"

    @property
    def summary(self) -> str:
        return "搜索历史故障记录"

    @property
    def prompt(self) -> str:
        return """\
搜索历史故障记录，查找相似事件的根因分析和修复方案。

## 参数
- query（必填）：搜索查询，描述当前症状或问题特征

## 适用场景
- 当前症状与某类已知问题模式相似，想参考历史修复方案
- 排查陷入僵局，需要从历史故障中寻找新思路
- 确认某个根因是否为反复出现的已知问题

## 使用原则
- gather_context 阶段已提供初始历史事件参考，仅在需要深入检索时使用
- 多角度搜索效果更好——按症状、按服务名、按错误类型分别搜索
- 历史事件是线索不是答案：相同症状可能不同根因
- 返回结果包含相似度评分，低相关结果已自动过滤"""

    def is_read_only(self, **kw) -> bool:
        return True

    def is_concurrency_safe(self, **kw) -> bool:
        return True

    async def check_permissions(self, **kw) -> PermissionResult:
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kw) -> str:
        from src.ops_agent.tools.history_tools import search_incident_history

        query = kw.get("query", "")
        text, _ = await search_incident_history(query=query)
        return text

    def _build_langchain_tool(self):
        tool_self = self

        async def _execute(query: str) -> str:
            result = await tool_self.execute(query=query)
            return truncate_output(result, tool_self.max_result_size_chars)

        return StructuredTool.from_function(
            coroutine=_execute,
            name=self.name,
            description=self.prompt,
        )
