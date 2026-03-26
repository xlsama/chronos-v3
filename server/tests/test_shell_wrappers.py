from src.ops_agent.ssh import SSHConnector
from src.ops_agent.tools.bash_tool import _wrap_local_command
from src.ops_agent.tools.ssh_bash_tool import _strip_stderr_discard
from src.ops_agent.tools.tool_classifier import CommandType, ShellSafety


def test_ssh_wrap_command_enables_pipefail_and_path():
    wrapped = SSHConnector._wrap_command("docker ps | head -20")

    assert "bash -lc" in wrapped
    assert "set -o pipefail;" in wrapped
    assert "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH;" in wrapped


def test_local_wrap_command_enables_pipefail():
    wrapped = _wrap_local_command("false | head -1")

    assert "bash -lc" in wrapped
    assert "set -o pipefail;" in wrapped


def test_sudo_read_classified_by_inner_content():
    assert ShellSafety.classify("sudo docker ps") is CommandType.READ
    assert ShellSafety.classify("sudo docker ps", local=True) is CommandType.READ


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


class TestStripStderrDiscard:
    def test_strips_basic_pattern(self):
        assert _strip_stderr_discard('docker ps -a 2>/dev/null || echo "no"') == 'docker ps -a || echo "no"'

    def test_strips_with_space(self):
        assert _strip_stderr_discard('docker ps 2> /dev/null') == 'docker ps'

    def test_strips_multiple_occurrences(self):
        result = _strip_stderr_discard('cmd1 2>/dev/null; cmd2 2> /dev/null')
        assert result == 'cmd1; cmd2'

    def test_preserves_command_without_pattern(self):
        cmd = 'docker ps -a 2>&1'
        assert _strip_stderr_discard(cmd) == cmd

    def test_preserves_empty_command(self):
        assert _strip_stderr_discard('') == ''
