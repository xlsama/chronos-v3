"""Root test fixtures: engine, session with savepoint rollback, app, client."""

import os
import subprocess
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

# Set test env vars BEFORE any src imports
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://chronos_test:chronos_test@localhost:15432/chronos_test"
)
os.environ["LANGGRAPH_CHECKPOINT_DSN"] = (
    "postgresql://chronos_test:chronos_test@localhost:15432/chronos_test"
)
os.environ["REDIS_URL"] = "redis://localhost:16379/0"
os.environ["ENCRYPTION_KEY"] = "dGVzdC1lbmNyeXB0aW9uLWtleS0zMmJ5dGVz"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# Clear all caches so they pick up test env
from src.env import get_settings

get_settings.cache_clear()

from src.db.connection import get_session
from src.lib.paths import get_data_dir

_TEST_DB_URL = get_settings().database_url
_migrations_done = False


def _ensure_migrations():
    global _migrations_done
    if not _migrations_done:
        subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            cwd=os.path.dirname(os.path.dirname(__file__)),  # server/
            env={**os.environ},
        )
        _migrations_done = True


@pytest.fixture(scope="session", autouse=True)
def _setup_test_data_dir(tmp_path_factory):
    """Create a temporary data directory for the test session."""
    data_dir = tmp_path_factory.mktemp("chronos_test_data")
    os.environ["DATA_DIR"] = str(data_dir)
    get_data_dir.cache_clear()
    get_settings.cache_clear()

    for sub in ["skills", "uploads", "knowledge", "incident_history"]:
        (data_dir / sub).mkdir()

    yield

    get_data_dir.cache_clear()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Per-test session with transaction rollback for isolation.

    Creates a fresh engine per test (NullPool = no pool overhead).
    Uses join_transaction_mode='create_savepoint' so app code's commit()
    only releases the savepoint, not the outer transaction.
    """
    _ensure_migrations()

    engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
    conn = await engine.connect()
    txn = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    yield session

    await session.close()
    await txn.rollback()
    await conn.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def app(db_session: AsyncSession):
    """FastAPI app with dependency overrides for testing."""
    from src.main import app as fastapi_app

    async def override_get_session():
        yield db_session

    fastapi_app.dependency_overrides[get_session] = override_get_session

    # Mock AgentRunner and publisher so background tasks don't fail
    mock_publisher = MagicMock()
    mock_publisher.publish = AsyncMock()
    mock_publisher.flush_remaining = AsyncMock()

    mock_runner = MagicMock()
    mock_runner.publisher = mock_publisher
    mock_runner.start = AsyncMock(return_value="test-thread-id")
    mock_runner.resume = AsyncMock()
    mock_runner.resume_with_human_input = AsyncMock()
    mock_runner.resume_after_interrupt = AsyncMock()
    mock_runner.graph = MagicMock()
    mock_runner.graph.aget_state = AsyncMock(return_value=MagicMock(next=[]))

    fastapi_app.state.agent_runner = mock_runner

    yield fastapi_app

    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient]:
    """HTTPX async client for API testing."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
