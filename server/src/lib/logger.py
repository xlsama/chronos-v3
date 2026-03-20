import os
import sys

from loguru import logger

_env = os.getenv("ENV", "development")
_default_level = "DEBUG" if _env == "development" else "INFO"
_log_level = os.getenv("LOG_LEVEL", _default_level)

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=_log_level,
)

_AGENT_COLORS: dict[str, str] = {
    "main":               "\033[1;33m[main]\033[0m",
    "gather_context":     "\033[34m[gather_context]\033[0m",
    "history_agent":      "\033[35m[history_agent]\033[0m",
    "kb_agent":           "\033[36m[kb_agent]\033[0m",
    "ask_human":          "\033[32m[ask_human]\033[0m",
    "approval":           "\033[31m[approval]\033[0m",
    "confirm_resolution": "\033[94m[confirm_resolution]\033[0m",
    "stream":             "\033[96m[stream]\033[0m",
    "skill":              "\033[95m[skill]\033[0m",
    "post_run":           "\033[92m[post_run]\033[0m",
}


def ac(component: str) -> str:
    return _AGENT_COLORS.get(component, f"[{component}]")


__all__ = ["logger", "ac"]
