from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.ops_agent.tools.base_tool import PermissionBehavior, PermissionResult
from src.ops_agent.tools.registry import get_tool

MISSING_APPROVAL_EXPLANATION_MESSAGE = (
    "该操作会触发人工审批，必须在 explanation 中说明操作原因、风险和预期影响。"
)


def normalize_explanation(explanation: Any) -> str:
    if explanation is None:
        return ""
    if isinstance(explanation, str):
        return explanation.strip()
    return str(explanation).strip()


def validate_approval_explanation(
    tool_args: Mapping[str, Any] | None, permission: PermissionResult
) -> str | None:
    if permission.behavior != PermissionBehavior.ASK:
        return None
    explanation = normalize_explanation((tool_args or {}).get("explanation"))
    if explanation:
        return None
    return MISSING_APPROVAL_EXPLANATION_MESSAGE


@dataclass(frozen=True)
class ToolApprovalContext:
    permission: PermissionResult
    explanation: str
    explanation_error: str | None


async def get_tool_approval_context(
    tool_name: str, tool_args: Mapping[str, Any] | None
) -> ToolApprovalContext | None:
    tool = get_tool(tool_name)
    if tool is None:
        return None

    args = dict(tool_args or {})
    permission = await tool.check_permissions(**args)
    explanation = normalize_explanation(args.get("explanation"))
    explanation_error = validate_approval_explanation(args, permission)
    return ToolApprovalContext(
        permission=permission,
        explanation=explanation,
        explanation_error=explanation_error,
    )


async def get_missing_approval_explanation_tool_name(message) -> str | None:
    if not hasattr(message, "tool_calls") or not message.tool_calls:
        return None

    for tool_call in message.tool_calls:
        context = await get_tool_approval_context(tool_call["name"], tool_call.get("args", {}))
        if context and context.explanation_error:
            return tool_call["name"]

    return None


def build_missing_approval_explanation_retry_message(tool_name: str) -> str:
    return (
        "[RETRY_TOOL_CALL]\n"
        f"你刚才调用的 `{tool_name}` 会触发人工审批，但没有提供 explanation。\n"
        "请重新调用该工具，并在 explanation 中写清操作原因、风险和预期影响。\n"
        "请重新回复，这次必须调用一个工具。"
    )
