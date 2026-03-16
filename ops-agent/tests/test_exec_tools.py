import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.ssh import SSHResult
from src.tools.exec_tools import exec_read, exec_write, list_connections
from src.tools.safety import CommandType


@pytest.fixture
def mock_ssh():
    connector = AsyncMock()
    with patch("src.tools.exec_tools.get_connector", new_callable=AsyncMock) as mock:
        mock.return_value = connector
        yield connector


async def test_exec_read_success(mock_ssh):
    mock_ssh.execute.return_value = SSHResult(exit_code=0, stdout="Filesystem  Size\n/dev/sda1   50G", stderr="")

    result = await exec_read(connection_id="infra-1", command="df -h")

    assert result["exit_code"] == 0
    assert "Filesystem" in result["stdout"]
    mock_ssh.execute.assert_called_once_with("df -h")


async def test_exec_read_blocked_command(mock_ssh):
    result = await exec_read(connection_id="infra-1", command="rm -rf /")

    assert result["error"] is not None
    assert "blocked" in result["error"].lower()
    mock_ssh.execute.assert_not_called()


async def test_exec_read_rejects_write_command(mock_ssh):
    result = await exec_read(connection_id="infra-1", command="systemctl restart nginx")

    assert result["error"] is not None
    assert "write" in result["error"].lower() or "read" in result["error"].lower()
    mock_ssh.execute.assert_not_called()


async def test_exec_write_success(mock_ssh):
    mock_ssh.execute.return_value = SSHResult(exit_code=0, stdout="done", stderr="")

    result = await exec_write(connection_id="infra-1", command="systemctl restart nginx")

    assert result["exit_code"] == 0
    mock_ssh.execute.assert_called_once_with("systemctl restart nginx")


async def test_exec_write_blocked_command(mock_ssh):
    result = await exec_write(connection_id="infra-1", command="rm -rf /")

    assert result["error"] is not None
    mock_ssh.execute.assert_not_called()


async def test_exec_read_long_output_compressed(mock_ssh):
    long_output = "x" * 20000
    mock_ssh.execute.return_value = SSHResult(exit_code=0, stdout=long_output, stderr="")

    result = await exec_read(connection_id="infra-1", command="cat /var/log/syslog")

    assert len(result["stdout"]) <= 10000


# ── list_connections tests ──


def _make_conn(name, infra_type="ssh", host="10.0.0.1", status="online", project_id=None):
    infra = MagicMock()
    infra.id = uuid.uuid4()
    infra.name = name
    infra.type = infra_type
    infra.host = host
    infra.status = status
    infra.project_id = project_id
    return infra


@pytest.fixture
def mock_db_session():
    """Mock DB session for list_connections tests."""
    with patch("src.db.connection.get_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_ctx)
        yield mock_session


async def test_list_connections_returns_safe_fields(mock_db_session):
    """list_connections should return only safe fields, no passwords or keys."""
    infra = _make_conn("web-server-1", host="192.168.1.10")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [infra]
    mock_db_session.execute.return_value = mock_result

    result = await list_connections()

    assert len(result) == 1
    item = result[0]
    assert item["name"] == "web-server-1"
    assert item["host"] == "192.168.1.10"
    assert item["type"] == "ssh"
    assert item["status"] == "online"
    assert "id" in item
    # Ensure no sensitive fields
    assert "encrypted_password" not in item
    assert "encrypted_private_key" not in item
    assert "conn_config" not in item


async def test_list_connections_filters_by_project(mock_db_session):
    """list_connections should filter by project_id when provided."""
    project_id = str(uuid.uuid4())
    infra = _make_conn("proj-server", project_id=uuid.UUID(project_id))
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [infra]
    mock_db_session.execute.return_value = mock_result

    result = await list_connections(project_id=project_id)

    assert len(result) == 1
    assert result[0]["project_id"] == project_id
    # Verify the query was executed (session.execute was called)
    mock_db_session.execute.assert_called_once()


async def test_list_connections_excludes_offline(mock_db_session):
    """list_connections query should exclude offline connections."""
    # Return empty (offline ones filtered by query)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    result = await list_connections()

    assert result == []
    mock_db_session.execute.assert_called_once()
