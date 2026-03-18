from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from .env import load_env, require_env

ROOT = Path(__file__).resolve().parents[3]
SERVER_DIR = ROOT / "server"
WEB_DIR = ROOT / "web"


class ProcessManager:
    def __init__(self) -> None:
        self._children: list[subprocess.Popen] = []

    def _test_env(self) -> dict[str, str]:
        load_env()
        env = {**os.environ}
        env.update(
            DATABASE_URL="postgresql+asyncpg://chronos:chronos@localhost:15432/chronos",
            LANGGRAPH_CHECKPOINT_DSN="postgresql://chronos:chronos@localhost:15432/chronos",
            REDIS_URL="redis://localhost:16379/0",
            DASHSCOPE_API_KEY=require_env("DASHSCOPE_API_KEY"),
        )
        return env

    def run_migrations(self) -> None:
        print("[proc] Running database migrations...")
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=SERVER_DIR,
            env=self._test_env(),
            check=True,
            timeout=60,
        )
        print("[proc] Migrations complete")

    def start_server(self) -> subprocess.Popen:
        print("[proc] Starting server...")
        child = subprocess.Popen(
            ["uv", "run", "uvicorn", "src.main:app", "--port", "8000"],
            cwd=SERVER_DIR,
            env=self._test_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._children.append(child)
        return child

    def start_frontend(self) -> subprocess.Popen:
        print("[proc] Starting frontend...")
        child = subprocess.Popen(
            ["pnpm", "dev", "--port", "5173"],
            cwd=WEB_DIR,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._children.append(child)
        return child

    def stop_all(self) -> None:
        print("[proc] Stopping all processes...")
        for child in self._children:
            try:
                child.send_signal(signal.SIGTERM)
                child.wait(timeout=10)
            except Exception:
                try:
                    child.kill()
                except Exception:
                    pass
        self._children.clear()
