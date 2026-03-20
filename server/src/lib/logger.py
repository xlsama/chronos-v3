import os
import re
import sys
import logging

import structlog
from rich.console import Console
from rich.rule import Rule
from rich.style import Style

_env = os.getenv("ENV", "development")
_default_level = "DEBUG" if _env == "development" else "INFO"
_log_level = os.getenv("LOG_LEVEL", _default_level)

# Rich Console（用于 Rule 渲染，模块级创建一次）
_rich_console = Console(file=sys.stderr, force_terminal=True, color_system="truecolor", width=80)

# 生命周期分隔线匹配
_LIFECYCLE_RE = re.compile(r"^={3,}\s*(.+?)\s*={3,}$")
_LIFECYCLE_RULE_STYLES: dict[str, str] = {
    "Agent lifecycle": "yellow bold",
    "Gathering context": "blue",
}

# 组件类别符号前缀
_COMPONENT_SYMBOLS: dict[str, str] = {
    "main": "*",
    "gather_context": ">", "history_agent": ">", "kb_agent": ">",
    "history": ">", "knowledge": ">",
    "bash": "$", "ssh_bash": "$", "ssh": "$", "service_exec": "$",
    "ask_human": "?", "approval": "?", "confirm_resolution": "?",
    "stream": "~", "skill": "#",
    "post_run": "+", "post_incident": "+",
    "retry": "!", "api": "-",
}

# 值高亮 Style（模块级预创建，避免每次调用分配）
_STYLE_GREEN = Style(color="green")
_STYLE_YELLOW = Style(color="yellow")
_STYLE_RED = Style(color="red", bold=True)
_STYLE_BRIGHT_WHITE = Style(color="bright_white", bold=True)
_STYLE_DIM = Style(dim=True)
_ELAPSED_RE = re.compile(r"^(\d+\.?\d*)s$")

# ── 组件颜色表 (rich Style) ──
_COMPONENT_STYLES: dict[str, Style] = {
    "main":               Style(color="yellow", bold=True),
    "gather_context":     Style(color="blue"),
    "history_agent":      Style(color="magenta"),
    "kb_agent":           Style(color="cyan"),
    "ask_human":          Style(color="green"),
    "approval":           Style(color="red"),
    "confirm_resolution": Style(color="bright_blue"),
    "stream":             Style(color="bright_cyan"),
    "skill":              Style(color="bright_magenta"),
    "post_run":           Style(color="bright_green"),
    "bash":               Style(color="yellow"),
    "ssh_bash":           Style(color="yellow"),
    "ssh":                Style(color="yellow"),
    "service_exec":       Style(color="yellow"),
    "history":            Style(color="magenta"),
    "knowledge":          Style(color="cyan"),
    "post_incident":      Style(color="bright_green"),
    "api":                Style(color="white"),
}


def _render_rule(title: str, style: str = "yellow") -> str:
    with _rich_console.capture() as capture:
        _rich_console.print(Rule(title, style=style))
    return capture.get().rstrip("\n")


def _lifecycle_rule_processor(_, __, event_dict):
    event = event_dict.get("event", "")
    m = _LIFECYCLE_RE.match(event)
    if not m:
        return event_dict
    title = m.group(1)
    rule_style = "yellow"
    for prefix, s in _LIFECYCLE_RULE_STYLES.items():
        if title.startswith(prefix):
            rule_style = s
            break
    parts = []
    ts = event_dict.get("timestamp", "")
    if ts:
        parts.append(_STYLE_DIM.render(ts))
    sid = event_dict.get("sid", "")
    if sid:
        parts.append(f"[{sid}]")
    rendered = _render_rule(title, style=rule_style)
    event_dict["_raw_output"] = " ".join(parts) + " " + rendered if parts else rendered
    return event_dict


def _colorize_component(_, __, event_dict):
    """processor: 给 component 加颜色"""
    comp = event_dict.get("component", "")
    if comp:
        style = _COMPONENT_STYLES.get(comp)
        symbol = _COMPONENT_SYMBOLS.get(comp, ".")
        tag = f"[{symbol} {comp}]"
        event_dict["component"] = style.render(tag) if style else tag
    return event_dict


def _highlight_values_processor(_, __, event_dict):
    # elapsed= : 绿(<2s) / 黄(2-5s) / 红(>5s)
    elapsed = event_dict.get("elapsed")
    if elapsed and isinstance(elapsed, str):
        m = _ELAPSED_RE.match(elapsed)
        if m:
            val = float(m.group(1))
            s = _STYLE_RED if val > 5.0 else (_STYLE_YELLOW if val > 2.0 else _STYLE_GREEN)
            event_dict["elapsed"] = s.render(elapsed)

    # exit_code= : 绿(0) / 红(非零)
    exit_code = event_dict.get("exit_code")
    if exit_code is not None:
        s = _STYLE_GREEN if exit_code == 0 else _STYLE_RED
        event_dict["exit_code"] = s.render(str(exit_code))

    # error= : 始终红色
    error = event_dict.get("error")
    if error and isinstance(error, str):
        event_dict["error"] = _STYLE_RED.render(error)

    # name= (工具名): 仅在工具相关上下文中高亮
    name = event_dict.get("name")
    if name and isinstance(name, str):
        ev = event_dict.get("event", "")
        if any(kw in ev for kw in ("tool_call", "Tool", "Executing", "Pending tool")):
            event_dict["name"] = _STYLE_BRIGHT_WHITE.render(name)

    # cmd_type= : READ(绿) / WRITE(黄) / DANGEROUS|BLOCKED(红)
    cmd_type = event_dict.get("cmd_type")
    if cmd_type and isinstance(cmd_type, str):
        if cmd_type == "READ":
            event_dict["cmd_type"] = _STYLE_GREEN.render(cmd_type)
        elif cmd_type == "WRITE":
            event_dict["cmd_type"] = _STYLE_YELLOW.render(cmd_type)
        elif cmd_type in ("DANGEROUS", "BLOCKED"):
            event_dict["cmd_type"] = _STYLE_RED.render(cmd_type)

    # decision= : approved(绿) / rejected(红)
    decision = event_dict.get("decision")
    if decision == "approved":
        event_dict["decision"] = _STYLE_GREEN.render(decision)
    elif decision == "rejected":
        event_dict["decision"] = _STYLE_RED.render(decision)

    return event_dict


class _EnhancedConsoleRenderer:
    def __init__(self, **kwargs):
        self._inner = structlog.dev.ConsoleRenderer(**kwargs)

    def __call__(self, logger, name, event_dict):
        raw = event_dict.pop("_raw_output", None)
        if raw is not None:
            return raw
        return self._inner(logger, name, event_dict)


def _prepend_component(_, __, event_dict):
    """processor: 把 [sid] [component] 移到 event 前面"""
    comp = event_dict.pop("component", "")
    sid = event_dict.pop("sid", "")
    parts = []
    if sid:
        parts.append(f"[{sid}]")
    if comp:
        parts.append(comp)
    if parts:
        event_dict["event"] = " ".join(parts) + " " + event_dict.get("event", "")
    return event_dict


shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.StackInfoRenderer(),
    structlog.dev.set_exc_info,
    structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
]

if _env == "development":
    structlog.configure(
        processors=[
            *shared_processors,
            _lifecycle_rule_processor,
            _colorize_component,
            _highlight_values_processor,
            _prepend_component,
            _EnhancedConsoleRenderer(colors=True, pad_event=40),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(_log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
else:
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(_log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(**binds) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(**binds)


logger = structlog.get_logger()

__all__ = ["logger", "get_logger"]
