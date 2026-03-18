from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

_loaded = False

SERVER_DIR = Path(__file__).resolve().parents[3] / "server"


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True

    env_path = SERVER_DIR / ".env"
    if env_path.exists():
        for key, value in dotenv_values(env_path).items():
            if value is not None:
                os.environ.setdefault(key, value)


def require_env(key: str) -> str:
    load_env()
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}. Set it in env or server/.env")
    return value
