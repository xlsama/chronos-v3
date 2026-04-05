"""上下文经济学 —— compact、prompt 组装、skills 上下文。"""

from .compact import (
    compact_conversation,
    compact_investigation_agent,
    compact_main_agent,
    is_context_limit_error,
    should_proactive_compact,
)
from .prompt_builder import (
    NO_TOOLS_PREAMBLE,
    OUTPUT_EFFICIENCY_SECTION,
    build_system_prompt,
    get_context_sections,
)
from .skills_context import build_skills_context

__all__ = [
    "compact_conversation",
    "compact_investigation_agent",
    "compact_main_agent",
    "is_context_limit_error",
    "should_proactive_compact",
    "get_context_sections",
    "build_system_prompt",
    "build_skills_context",
    "NO_TOOLS_PREAMBLE",
    "OUTPUT_EFFICIENCY_SECTION",
]
