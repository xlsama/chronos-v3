import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# 路径设置
SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"
os.chdir(SERVER_DIR)
sys.path.insert(0, str(SERVER_DIR))


# --- pytest 自定义选项 ---
def pytest_addoption(parser):
    parser.addoption("--project-id", default="f5b3cf38-252c-4f44-8a08-03b7151075ee")


# --- Fixtures ---
@pytest.fixture(scope="session")
def project_id(request):
    return request.config.getoption("--project-id")


@pytest_asyncio.fixture(scope="session")
async def embedder():
    from src.lib.embedder import Embedder

    return Embedder()


@pytest_asyncio.fixture(scope="session")
async def reranker():
    from src.lib.reranker import Reranker

    return Reranker()


@pytest_asyncio.fixture
async def db_session():
    from src.db.connection import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture
def event_callback():
    """收集事件的 callback，测试后可检查事件列表"""
    events = []

    async def _cb(event_type, data):
        events.append((event_type, data))

    _cb.events = events
    return _cb
