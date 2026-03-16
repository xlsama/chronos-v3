"""Tests for ServiceCatalog — service discovery and CRUD."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.service_catalog import ServiceCatalog


class TestServiceCatalogCRUD:
    @pytest.fixture
    def session(self):
        session = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def catalog(self, session):
        return ServiceCatalog(session=session)

    async def test_create(self, catalog, session):
        conn_id = uuid.uuid4()
        result = await catalog.create(
            connection_id=conn_id,
            name="nginx",
            port=80,
        )

        assert result.name == "nginx"
        assert result.port == 80
        assert result.connection_id == conn_id
        session.add.assert_called_once()
        session.commit.assert_called_once()

    async def test_list_by_connection(self, catalog, session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        result = await catalog.list_by_connection(uuid.uuid4())

        assert result == []

    async def test_delete_success(self, catalog, session):
        mock_svc = MagicMock()
        session.get.return_value = mock_svc

        ok = await catalog.delete(uuid.uuid4())

        assert ok is True
        session.delete.assert_called_once_with(mock_svc)
        session.commit.assert_called_once()

    async def test_delete_not_found(self, catalog, session):
        session.get.return_value = None

        ok = await catalog.delete(uuid.uuid4())

        assert ok is False
        session.delete.assert_not_called()


class TestAutoDiscoverSSH:
    @pytest.fixture
    def session(self):
        session = AsyncMock()
        session.add = MagicMock()
        # _create_if_not_exists calls session.execute to check existence → return None
        mock_no_existing = MagicMock()
        mock_no_existing.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_no_existing
        return session

    @pytest.fixture
    def catalog(self, session):
        return ServiceCatalog(session=session)

    @patch("src.services.service_catalog.get_connector")
    async def test_discover_ssh_docker(self, mock_get_connector, catalog, session):
        conn_id = uuid.uuid4()
        mock_conn = MagicMock()
        mock_conn.type = "ssh"
        session.get.return_value = mock_conn

        mock_connector = AsyncMock()
        mock_get_connector.return_value = mock_connector

        # Docker ps output (name + ports only, no image)
        docker_output = "nginx\t0.0.0.0:80->80/tcp\nredis\t0.0.0.0:6379->6379/tcp"
        mock_connector.execute.side_effect = [
            MagicMock(exit_code=0, stdout=docker_output),  # docker ps
            MagicMock(exit_code=1, stdout=""),  # systemctl (fail)
            MagicMock(exit_code=1, stdout=""),  # ss (fail)
            MagicMock(exit_code=1, stdout=""),  # crontab (fail)
        ]

        discovered = await catalog.auto_discover(conn_id)

        assert len(discovered) == 2
        assert discovered[0].name == "nginx"
        assert discovered[0].port == 80
        assert discovered[1].name == "redis"
        assert discovered[1].port == 6379

    @patch("src.services.service_catalog.get_connector")
    async def test_discover_ssh_systemd(self, mock_get_connector, catalog, session):
        conn_id = uuid.uuid4()
        mock_conn = MagicMock()
        mock_conn.type = "ssh"
        session.get.return_value = mock_conn

        mock_connector = AsyncMock()
        mock_get_connector.return_value = mock_connector

        systemd_output = "nginx.service loaded active running\npostgresql.service loaded active running"
        mock_connector.execute.side_effect = [
            MagicMock(exit_code=1, stdout=""),  # docker ps (fail)
            MagicMock(exit_code=0, stdout=systemd_output),  # systemctl
            MagicMock(exit_code=1, stdout=""),  # ss (fail)
            MagicMock(exit_code=1, stdout=""),  # crontab (fail)
        ]

        discovered = await catalog.auto_discover(conn_id)

        assert len(discovered) == 2
        names = [s.name for s in discovered]
        assert "nginx" in names
        assert "postgresql" in names


class TestAutoDiscoverK8s:
    @pytest.fixture
    def session(self):
        session = AsyncMock()
        session.add = MagicMock()
        mock_no_existing = MagicMock()
        mock_no_existing.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_no_existing
        return session

    @pytest.fixture
    def catalog(self, session):
        return ServiceCatalog(session=session)

    @patch("src.services.service_catalog.get_connector")
    async def test_discover_k8s(self, mock_get_connector, catalog, session):
        conn_id = uuid.uuid4()
        mock_conn = MagicMock()
        mock_conn.type = "kubernetes"
        session.get.return_value = mock_conn

        mock_connector = AsyncMock()
        mock_get_connector.return_value = mock_connector

        deployments_output = "default   nginx\nkube-system   coredns"
        statefulsets_output = "default   postgres"

        mock_connector.execute.side_effect = [
            MagicMock(exit_code=0, stdout=deployments_output),
            MagicMock(exit_code=0, stdout=statefulsets_output),
        ]

        discovered = await catalog.auto_discover(conn_id)

        names = [s.name for s in discovered]
        assert "nginx" in names
        assert "coredns" in names
        assert "postgres" in names


class TestHelperMethods:
    def test_is_interesting_service_filters_system(self):
        assert ServiceCatalog._is_interesting_service("nginx") is True
        assert ServiceCatalog._is_interesting_service("postgresql") is True
        assert ServiceCatalog._is_interesting_service("systemd") is False
        assert ServiceCatalog._is_interesting_service("sshd") is False
        assert ServiceCatalog._is_interesting_service("dbus") is False

    def test_extract_port_arrow_format(self):
        assert ServiceCatalog._extract_port("0.0.0.0:80->80/tcp") == 80
        assert ServiceCatalog._extract_port("0.0.0.0:3306->3306/tcp") == 3306

    def test_extract_port_colon_format(self):
        assert ServiceCatalog._extract_port(":8080") == 8080

    def test_extract_port_no_port(self):
        assert ServiceCatalog._extract_port("") is None
        assert ServiceCatalog._extract_port("no-port-here") is None
