"""Tests for ProjectService — CRUD + slug auto-generation."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.project_service import ProjectService


class TestProjectService:
    @pytest.fixture
    def session(self):
        session = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def service(self, session):
        return ProjectService(session=session)

    async def test_create_with_explicit_slug(self, service, session):
        result = await service.create(name="My Project", slug="my-project", description="desc")

        assert result.name == "My Project"
        assert result.slug == "my-project"
        assert result.description == "desc"
        session.add.assert_called_once()
        session.commit.assert_called_once()

    async def test_create_auto_generates_slug(self, service, session):
        # Mock execute to return empty result for slug uniqueness check
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await service.create(name="My Project")

        assert result.slug == "my-project"

    async def test_create_with_cloud_md(self, service, session):
        result = await service.create(
            name="Proj", slug="proj", cloud_md="# Cloud Architecture"
        )

        assert result.cloud_md == "# Cloud Architecture"

    async def test_update_cloud_md(self, service, session):
        project = MagicMock()
        project.cloud_md = None

        result = await service.update_cloud_md(project, "# New Cloud MD")

        assert project.cloud_md == "# New Cloud MD"
        session.commit.assert_called_once()

    async def test_get_by_slug(self, service, session):
        mock_project = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        session.execute.return_value = mock_result

        result = await service.get_by_slug("my-project")

        assert result == mock_project

    async def test_list_projects(self, service, session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        result = await service.list()

        assert result == []

    async def test_delete(self, service, session):
        project = MagicMock()

        await service.delete(project)

        session.delete.assert_called_once_with(project)
        session.commit.assert_called_once()

    async def test_update(self, service, session):
        project = MagicMock()
        project.name = "Old"

        result = await service.update(project, name="New", description="Updated")

        assert project.name == "New"
        assert project.description == "Updated"
        session.commit.assert_called_once()
