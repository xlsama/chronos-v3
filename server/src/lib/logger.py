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

__all__ = ["logger"]
