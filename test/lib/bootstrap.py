"""Shared test infrastructure for manual Python test scripts."""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# --- Path setup: ensure server/src is importable and .env is found ---
SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"
os.chdir(SERVER_DIR)
sys.path.insert(0, str(SERVER_DIR))

# Singletons
_embedder = None
_reranker = None


def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@asynccontextmanager
async def get_session():
    """Provide an async DB session."""
    from src.db.connection import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


def get_embedder():
    """Return a singleton Embedder instance."""
    global _embedder
    if _embedder is None:
        from src.lib.embedder import Embedder
        _embedder = Embedder()
    return _embedder


def get_reranker():
    """Return a singleton Reranker instance."""
    global _reranker
    if _reranker is None:
        from src.lib.reranker import Reranker
        _reranker = Reranker()
    return _reranker


async def console_event_callback(event_type: str, data: dict) -> None:
    """Print Sub-Agent events to console for debugging."""
    if event_type == "thinking":
        content = data.get("content", "")
        if content:
            print(content, end="", flush=True)
    elif event_type == "thinking_done":
        print()
    elif event_type == "tool_call":
        name = data.get("name", "")
        args = data.get("args", {})
        print_divider(f"Tool Call: {name}")
        for k, v in args.items():
            print(f"  {k}: {v}")
    elif event_type == "tool_result":
        name = data.get("name", "")
        output = data.get("output", "")
        sources = data.get("sources", [])
        print_divider(f"Tool Result: {name}")
        print(output[:2000])
        if len(output) > 2000:
            print(f"  ... ({len(output)} chars total)")
        if sources:
            print(f"  Sources: {sources}")


def print_divider(title: str = "") -> None:
    """Print a formatted divider line."""
    if title:
        print(f"\n{'=' * 20} {title} {'=' * 20}")
    else:
        print(f"\n{'=' * 60}")
