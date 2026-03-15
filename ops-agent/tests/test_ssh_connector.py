from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.ssh import SSHConnector, SSHResult


@pytest.fixture
def connector():
    return SSHConnector(host="192.168.1.1", port=22, username="root", password="secret")


def _mock_paramiko_client(exit_status=0, stdout_data="output", stderr_data=""):
    mock_client = MagicMock()
    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    mock_stdout.read.return_value = stdout_data.encode()
    mock_stderr.read.return_value = stderr_data.encode()
    mock_stdout.channel.recv_exit_status.return_value = exit_status
    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
    return mock_client


@patch("src.connectors.ssh.paramiko.SSHClient")
async def test_execute_command(mock_ssh_class, connector: SSHConnector):
    mock_client = _mock_paramiko_client(stdout_data="hello world")
    mock_ssh_class.return_value = mock_client

    result = await connector.execute("echo hello")

    assert isinstance(result, SSHResult)
    assert result.exit_code == 0
    assert result.stdout == "hello world"
    assert result.stderr == ""
    mock_client.connect.assert_called_once()
    mock_client.close.assert_called_once()


@patch("src.connectors.ssh.paramiko.SSHClient")
async def test_execute_command_with_error(mock_ssh_class, connector: SSHConnector):
    mock_client = _mock_paramiko_client(exit_status=1, stderr_data="not found")
    mock_ssh_class.return_value = mock_client

    result = await connector.execute("cat /nonexistent")

    assert result.exit_code == 1
    assert result.stderr == "not found"


@patch("src.connectors.ssh.paramiko.SSHClient")
async def test_test_connection_success(mock_ssh_class, connector: SSHConnector):
    mock_client = _mock_paramiko_client(stdout_data="ok")
    mock_ssh_class.return_value = mock_client

    ok = await connector.test_connection()
    assert ok is True


@patch("src.connectors.ssh.paramiko.SSHClient")
async def test_test_connection_failure(mock_ssh_class, connector: SSHConnector):
    mock_client = MagicMock()
    mock_client.connect.side_effect = Exception("Connection refused")
    mock_ssh_class.return_value = mock_client

    ok = await connector.test_connection()
    assert ok is False


def test_ssh_connector_with_key():
    connector = SSHConnector(
        host="192.168.1.1", port=22, username="root", private_key="ssh-rsa AAAA..."
    )
    assert connector.private_key == "ssh-rsa AAAA..."
    assert connector.password is None
