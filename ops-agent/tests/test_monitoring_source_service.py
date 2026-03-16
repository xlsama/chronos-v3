"""Tests for MonitoringSourceService."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.monitoring_source_service import MonitoringSourceService


class TestMonitoringSourceService:
    @pytest.fixture
    def session(self):
        session = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def crypto(self):
        crypto = MagicMock()
        crypto.encrypt.side_effect = lambda x: f"enc:{x}"
        crypto.decrypt.side_effect = lambda x: x.replace("enc:", "")
        return crypto

    @pytest.fixture
    def service(self, session, crypto):
        return MonitoringSourceService(session=session, crypto=crypto)

    async def test_create_with_auth_header(self, service, session, crypto):
        project_id = uuid.uuid4()
        result = await service.create(
            project_id=project_id,
            name="Prod Prometheus",
            source_type="prometheus",
            endpoint="http://prometheus:9090",
            auth_header="Bearer secret-token",
        )

        assert result.name == "Prod Prometheus"
        assert result.source_type == "prometheus"
        assert result.endpoint == "http://prometheus:9090"
        assert result.conn_config is not None
        crypto.encrypt.assert_called_once()
        session.add.assert_called_once()
        session.commit.assert_called_once()

    async def test_create_without_auth_header(self, service, session, crypto):
        project_id = uuid.uuid4()
        result = await service.create(
            project_id=project_id,
            name="Loki",
            source_type="loki",
            endpoint="http://loki:3100",
        )

        assert result.conn_config is None
        crypto.encrypt.assert_not_called()

    async def test_list_by_project(self, service, session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        result = await service.list_by_project(uuid.uuid4())

        assert result == []

    async def test_delete_success(self, service, session):
        mock_source = MagicMock()
        session.get.return_value = mock_source

        ok = await service.delete(uuid.uuid4())

        assert ok is True
        session.delete.assert_called_once_with(mock_source)
        session.commit.assert_called_once()

    async def test_delete_not_found(self, service, session):
        session.get.return_value = None

        ok = await service.delete(uuid.uuid4())

        assert ok is False
        session.delete.assert_not_called()

    async def test_has_source_types(self, service, session):
        mock_prom = MagicMock()
        mock_prom.source_type = "prometheus"
        mock_loki = MagicMock()
        mock_loki.source_type = "loki"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_prom, mock_loki]
        session.execute.return_value = mock_result

        has_prom, has_loki = await service.has_source_types(uuid.uuid4())

        assert has_prom is True
        assert has_loki is True

    async def test_has_source_types_none(self, service, session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        has_prom, has_loki = await service.has_source_types(uuid.uuid4())

        assert has_prom is False
        assert has_loki is False

    async def test_has_source_types_partial(self, service, session):
        mock_prom = MagicMock()
        mock_prom.source_type = "prometheus"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_prom]
        session.execute.return_value = mock_result

        has_prom, has_loki = await service.has_source_types(uuid.uuid4())

        assert has_prom is True
        assert has_loki is False
