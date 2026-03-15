from unittest.mock import AsyncMock, patch

import pytest

from src.connectors.ssh import SSHResult
from src.tools.exec_tools import exec_read, exec_write
from src.tools.safety import CommandType


@pytest.fixture
def mock_ssh():
    with patch("src.tools.exec_tools.get_ssh_connector") as mock:
        connector = AsyncMock()
        mock.return_value = connector
        yield connector


async def test_exec_read_success(mock_ssh):
    mock_ssh.execute.return_value = SSHResult(exit_code=0, stdout="Filesystem  Size\n/dev/sda1   50G", stderr="")

    result = await exec_read(infra_id="infra-1", command="df -h")

    assert result["exit_code"] == 0
    assert "Filesystem" in result["stdout"]
    mock_ssh.execute.assert_called_once_with("df -h")


async def test_exec_read_blocked_command(mock_ssh):
    result = await exec_read(infra_id="infra-1", command="rm -rf /")

    assert result["error"] is not None
    assert "blocked" in result["error"].lower()
    mock_ssh.execute.assert_not_called()


async def test_exec_read_rejects_write_command(mock_ssh):
    result = await exec_read(infra_id="infra-1", command="systemctl restart nginx")

    assert result["error"] is not None
    assert "write" in result["error"].lower() or "read" in result["error"].lower()
    mock_ssh.execute.assert_not_called()


async def test_exec_write_success(mock_ssh):
    mock_ssh.execute.return_value = SSHResult(exit_code=0, stdout="done", stderr="")

    result = await exec_write(infra_id="infra-1", command="systemctl restart nginx")

    assert result["exit_code"] == 0
    mock_ssh.execute.assert_called_once_with("systemctl restart nginx")


async def test_exec_write_blocked_command(mock_ssh):
    result = await exec_write(infra_id="infra-1", command="rm -rf /")

    assert result["error"] is not None
    mock_ssh.execute.assert_not_called()


async def test_exec_read_long_output_compressed(mock_ssh):
    long_output = "x" * 20000
    mock_ssh.execute.return_value = SSHResult(exit_code=0, stdout=long_output, stderr="")

    result = await exec_read(infra_id="infra-1", command="cat /var/log/syslog")

    assert len(result["stdout"]) <= 10000
