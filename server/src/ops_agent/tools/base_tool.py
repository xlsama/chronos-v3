"""Chronos V3 Tool 协议 —— 所有 Agent 工具的统一接口。

借鉴 Claude Code 的 Tool 设计，提供：
- 身份（name / summary / prompt）
- 元数据（read-only / destructive / concurrency-safe）
- 统一权限检查（check_permissions → ALLOW / ASK / DENY）
- 输出截断
- LangChain 桥接（to_langchain_tool → StructuredTool）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PermissionBehavior(str, Enum):
    ALLOW = "allow"  # 自动执行
    ASK = "ask"  # 需人工审批
    DENY = "deny"  # 直接拒绝


@dataclass(frozen=True)
class PermissionResult:
    behavior: PermissionBehavior
    reason: str = ""
    risk_level: str = ""  # "MEDIUM" | "HIGH"，仅 ASK 时有意义


class BaseTool(ABC):
    """Chronos V3 Ops Agent 工具协议。

    Fail-closed 默认值：
    - is_read_only → False
    - is_destructive → False
    - is_concurrency_safe → False
    工具必须显式声明自己是只读或可并发的。
    """

    def __init__(self):
        self._lc_tool_cache = None

    # ── 身份 ──

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识符，如 "ssh_bash"。"""
        ...

    @property
    @abstractmethod
    def summary(self) -> str:
        """一句话描述，用于日志和 UI 展示。"""
        ...

    @property
    @abstractmethod
    def prompt(self) -> str:
        """完整的 LLM 工具描述，包含使用指南、注意事项、最佳实践。

        此文本作为 tool definition 的 description 字段传给 LLM。
        """
        ...

    @property
    def max_result_size_chars(self) -> int:
        """输出截断阈值（字符数）。子类可覆盖。"""
        return 30_000

    # ── 分类元数据 ──

    @abstractmethod
    def is_read_only(self, **kwargs: Any) -> bool:
        """当前调用是否只读。"""
        ...

    def is_destructive(self, **kwargs: Any) -> bool:
        """当前调用是否具有破坏性。"""
        return False

    def is_concurrency_safe(self, **kwargs: Any) -> bool:
        """当前调用是否可安全并发。"""
        return False

    # ── 权限 ──

    @abstractmethod
    async def check_permissions(self, **kwargs: Any) -> PermissionResult:
        """权限检查 —— 权限判定的唯一入口。"""
        ...

    # ── 执行 ──

    def validate_input(self, **kwargs: Any) -> str | None:
        """输入校验。返回错误信息字符串，或 None 表示通过。默认不校验。"""
        return None

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """执行工具。子类实现具体逻辑。"""
        ...

    async def post_execute(self, result: Any, **kwargs: Any) -> Any:
        """执行后处理。默认直接返回结果。"""
        return result

    async def execute_pipeline(self, **kwargs: Any) -> Any:
        """统一执行管道：validate → execute → truncate → post_execute。"""
        from src.ops_agent.tools.truncation import truncate_output

        error = self.validate_input(**kwargs)
        if error:
            return error
        result = await self.execute(**kwargs)
        result = truncate_output(result, self.max_result_size_chars)
        return await self.post_execute(result, **kwargs)

    # ── LangChain 桥接 ──

    def to_langchain_tool(self):
        """创建 LangChain 兼容的 StructuredTool，供 LangGraph ToolNode 使用。

        结果会缓存，多次调用返回同一实例。
        子类必须实现 _build_langchain_tool()。
        """
        if self._lc_tool_cache is None:
            self._lc_tool_cache = self._build_langchain_tool()
        return self._lc_tool_cache

    @abstractmethod
    def _build_langchain_tool(self):
        """构建 LangChain StructuredTool。子类实现。"""
        ...
