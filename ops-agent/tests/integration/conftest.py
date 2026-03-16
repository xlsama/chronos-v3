"""Integration test fixtures — requires real PostgreSQL + pgvector + DASHSCOPE_API_KEY."""

import os
import shutil
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import DocumentChunk, Project, ProjectDocument
from src.lib.embedder import Embedder
from src.lib.image_describer import ImageDescriber
from src.lib.reranker import Reranker

_SKIP_REASON = "Integration tests require DASHSCOPE_API_KEY and PostgreSQL with pgvector"


def _should_skip() -> bool:
    return not os.environ.get("DASHSCOPE_API_KEY")


def _get_db_url() -> str:
    from src.config import get_settings
    return get_settings().database_url


# ── Per-test session ──


@pytest.fixture
async def db_session():
    if _should_skip():
        pytest.skip(_SKIP_REASON)

    engine = create_async_engine(_get_db_url(), echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session

    await engine.dispose()


# ── Test project (with cleanup) ──


@pytest.fixture
async def test_project(db_session: AsyncSession):
    slug = f"inttest-{uuid.uuid4().hex[:8]}"
    project = Project(
        name=f"Integration Test {slug}",
        slug=slug,
        description="Auto-created by integration test",
        service_md="# 服务架构\nNginx + MySQL 主从",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    yield project

    # Cleanup: delete chunks → documents → project
    await db_session.execute(
        delete(DocumentChunk).where(DocumentChunk.project_id == project.id)
    )
    await db_session.execute(
        delete(ProjectDocument).where(ProjectDocument.project_id == project.id)
    )
    await db_session.execute(
        delete(Project).where(Project.id == project.id)
    )
    await db_session.commit()

    # Cleanup filesystem
    knowledge_dir = f"data/knowledge/{slug}"
    if os.path.exists(knowledge_dir):
        shutil.rmtree(knowledge_dir)


# ── Real service instances ──


@pytest.fixture
def real_embedder():
    return Embedder()


@pytest.fixture
def real_reranker():
    return Reranker()


@pytest.fixture
def real_image_describer():
    return ImageDescriber()
