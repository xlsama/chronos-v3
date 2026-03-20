import os
import sys
import logging

import structlog

_env = os.getenv("ENV", "development")
_default_level = "DEBUG" if _env == "development" else "INFO"
_log_level = os.getenv("LOG_LEVEL", _default_level)

# ── 组件颜色表 (ANSI) ──
COMPONENT_COLORS: dict[str, str] = {
    "main":               "\033[1;33m",   # bold yellow
    "gather_context":     "\033[34m",     # blue
    "history_agent":      "\033[35m",     # magenta
    "kb_agent":           "\033[36m",     # cyan
    "ask_human":          "\033[32m",     # green
    "approval":           "\033[31m",     # red
    "confirm_resolution": "\033[94m",     # bright blue
    "stream":             "\033[96m",     # bright cyan
    "skill":              "\033[95m",     # bright magenta
    "post_run":           "\033[92m",     # bright green
    "bash":               "\033[33m",     # yellow
    "ssh_bash":           "\033[33m",     # yellow
    "ssh":                "\033[33m",     # yellow
    "service_exec":       "\033[33m",     # yellow
    "history":            "\033[35m",     # magenta
    "knowledge":          "\033[36m",     # cyan
    "post_incident":      "\033[92m",     # bright green
    "api":                "\033[37m",     # white
}
_RESET = "\033[0m"


def _colorize_component(_, __, event_dict):
    """processor: 给 component 加 ANSI 颜色"""
    comp = event_dict.get("component", "")
    if comp:
        color = COMPONENT_COLORS.get(comp, "")
        event_dict["component"] = f"{color}[{comp}]{_RESET}" if color else f"[{comp}]"
    return event_dict


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
            _colorize_component,
            _prepend_component,
            structlog.dev.ConsoleRenderer(colors=True, pad_event=40),
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
