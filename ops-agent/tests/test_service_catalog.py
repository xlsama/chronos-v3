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
        infra_id = uuid.uuid4()
        result = await catalog.create(
            infrastructure_id=infra_id,
            name="nginx",
            service_type="nginx",
            port=80,
        )

        assert result.name == "nginx"
        assert result.service_type == "nginx"
        assert result.port == 80
        assert result.infrastructure_id == infra_id
        session.add.assert_called_once()
        session.commit.assert_called_once()

    async def test_list_by_infra(self, catalog, session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        result = await catalog.list_by_infra(uuid.uuid4())

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
        infra_id = uuid.uuid4()
        mock_infra = MagicMock()
        mock_infra.type = "ssh"
        session.get.return_value = mock_infra

        mock_connector = AsyncMock()
        mock_get_connector.return_value = mock_connector

        # Docker ps output
        docker_output = "nginx\t0.0.0.0:80->80/tcp\tnginx:latest\nredis\t0.0.0.0:6379->6379/tcp\tredis:7"
        mock_connector.execute.side_effect = [
            MagicMock(exit_code=0, stdout=docker_output),  # docker ps
            MagicMock(exit_code=1, stdout=""),  # systemctl (fail)
            MagicMock(exit_code=1, stdout=""),  # ss (fail)
            MagicMock(exit_code=1, stdout=""),  # crontab (fail)
        ]

        discovered = await catalog.auto_discover(infra_id)

        assert len(discovered) == 2
        assert discovered[0].name == "nginx"
        assert discovered[0].service_type == "nginx"
        assert discovered[0].port == 80
        assert discovered[1].name == "redis"
        assert discovered[1].service_type == "redis"
        assert discovered[1].port == 6379

    @patch("src.services.service_catalog.get_connector")
    async def test_discover_ssh_systemd(self, mock_get_connector, catalog, session):
        infra_id = uuid.uuid4()
        mock_infra = MagicMock()
        mock_infra.type = "ssh"
        session.get.return_value = mock_infra

        mock_connector = AsyncMock()
        mock_get_connector.return_value = mock_connector

        systemd_output = "nginx.service loaded active running\npostgresql.service loaded active running"
        mock_connector.execute.side_effect = [
            MagicMock(exit_code=1, stdout=""),  # docker ps (fail)
            MagicMock(exit_code=0, stdout=systemd_output),  # systemctl
            MagicMock(exit_code=1, stdout=""),  # ss (fail)
            MagicMock(exit_code=1, stdout=""),  # crontab (fail)
        ]

        discovered = await catalog.auto_discover(infra_id)

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
        infra_id = uuid.uuid4()
        mock_infra = MagicMock()
        mock_infra.type = "kubernetes"
        session.get.return_value = mock_infra

        mock_connector = AsyncMock()
        mock_get_connector.return_value = mock_connector

        deployments_output = "default   nginx\nkube-system   coredns"
        statefulsets_output = "default   postgres"

        mock_connector.execute.side_effect = [
            MagicMock(exit_code=0, stdout=deployments_output),
            MagicMock(exit_code=0, stdout=statefulsets_output),
        ]

        discovered = await catalog.auto_discover(infra_id)

        types = [s.service_type for s in discovered]
        names = [s.name for s in discovered]
        assert "k8s_deployment" in types
        assert "k8s_statefulset" in types
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

    def test_guess_service_type_by_port(self):
        assert ServiceCatalog._guess_service_type("mysqld", 3306) == "mysql"
        assert ServiceCatalog._guess_service_type("pg_main", 5432) == "postgresql"
        assert ServiceCatalog._guess_service_type("mongod", 27017) == "mongodb"
        assert ServiceCatalog._guess_service_type("redis-server", 6379) == "redis"
        assert ServiceCatalog._guess_service_type("es", 9200) == "elasticsearch"

    def test_guess_service_type_by_name(self):
        assert ServiceCatalog._guess_service_type("nginx", 80) == "nginx"
        assert ServiceCatalog._guess_service_type("node", 3000) == "node_app"
        assert ServiceCatalog._guess_service_type("java", 8080) == "java_app"
        assert ServiceCatalog._guess_service_type("gunicorn", 8000) == "python_app"
        assert ServiceCatalog._guess_service_type("httpd", 80) == "apache"

    def test_guess_service_type_default(self):
        assert ServiceCatalog._guess_service_type("unknown-proc", 9999) == "custom"

    def test_guess_type_from_image(self):
        assert ServiceCatalog._guess_type_from_image("nginx:latest") == "nginx"
        assert ServiceCatalog._guess_type_from_image("library/mysql:8") == "mysql"
        assert ServiceCatalog._guess_type_from_image("redis:7") == "redis"
        assert ServiceCatalog._guess_type_from_image("postgres:15-alpine") == "postgresql"
        assert ServiceCatalog._guess_type_from_image("mongo:6") == "mongodb"
        assert ServiceCatalog._guess_type_from_image("custom-app:v1") is None
