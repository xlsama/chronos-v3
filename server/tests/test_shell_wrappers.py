from src.ops_agent.ssh import SSHConnector
from src.ops_agent.tools.bash_tool import _wrap_local_command
from src.ops_agent.tools.tool_permissions import CommandType, ShellSafety


def test_ssh_wrap_command_enables_pipefail_and_path():
    wrapped = SSHConnector._wrap_command("docker ps | head -20")

    assert "bash -lc" in wrapped
    assert "set -o pipefail;" in wrapped
    assert "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH;" in wrapped


def test_local_wrap_command_enables_pipefail():
    wrapped = _wrap_local_command("false | head -1")

    assert "bash -lc" in wrapped
    assert "set -o pipefail;" in wrapped


def test_remote_sudo_read_is_write_and_local_sudo_is_blocked():
    assert ShellSafety.classify("sudo docker ps") is CommandType.WRITE
    assert ShellSafety.classify("sudo docker ps", local=True) is CommandType.BLOCKED


def test_prepare_command_uses_sudo_password():
    connector = SSHConnector(host="example.com", username="admin", password="ssh_pw", sudo_password="secret")

    prepared, stdin_input = connector._prepare_command("sudo docker ps")

    assert prepared.startswith("sudo -S -p '' docker ps")
    assert stdin_input == "secret\n"


def test_prepare_command_uses_non_interactive_sudo_without_password():
    connector = SSHConnector(host="example.com", username="admin")

    prepared, stdin_input = connector._prepare_command("sudo docker ps")

    assert prepared.startswith("sudo -n docker ps")
    assert stdin_input is None
