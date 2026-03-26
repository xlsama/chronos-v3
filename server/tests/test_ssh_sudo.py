from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ops_agent.ssh import SSHConnector
from src.ops_agent.tools.tool_classifier import CommandType, ShellSafety
from src.services.crypto import CryptoService
from src.services.server_service import ServerService


class TestPrepareCommand:
    """Tests for SSHConnector._prepare_command() sudo handling."""

    def _make_connector(self, sudo_password: str | None = None) -> SSHConnector:
        return SSHConnector(host="10.0.0.1", password="ssh_pass", sudo_password=sudo_password)

    def test_no_sudo_returns_unchanged(self):
        c = self._make_connector(sudo_password="secret")
        cmd, stdin = c._prepare_command("docker ps")
        assert cmd == "docker ps"
        assert stdin is None

    def test_sudo_with_password_rewrites_to_sudo_s(self):
        c = self._make_connector(sudo_password="secret")
        cmd, stdin = c._prepare_command("sudo docker ps")
        assert "sudo -S -p ''" in cmd
        assert "docker ps" in cmd
        assert stdin == "secret\n"

    def test_sudo_without_password_rewrites_to_sudo_n(self):
        c = self._make_connector(sudo_password=None)
        cmd, stdin = c._prepare_command("sudo docker ps")
        assert "sudo -n" in cmd
        assert stdin is None

    def test_sudo_s_already_present_not_duplicated(self):
        c = self._make_connector(sudo_password="secret")
        cmd, stdin = c._prepare_command("sudo -S docker ps")
        assert cmd == "sudo -S docker ps"
        assert stdin == "secret\n"

    def test_sudo_n_already_present_not_duplicated(self):
        c = self._make_connector(sudo_password="secret")
        cmd, stdin = c._prepare_command("sudo -n docker ps")
        assert cmd == "sudo -n docker ps"
        assert stdin is None

    def test_sudo_with_other_flags(self):
        c = self._make_connector(sudo_password="secret")
        cmd, stdin = c._prepare_command("sudo -u www docker ps")
        assert "sudo -S -p ''" in cmd
        assert "-u www" in cmd
        assert stdin == "secret\n"

    def test_non_sudo_prefix_not_matched(self):
        """'sudoers' should not trigger sudo rewriting."""
        c = self._make_connector(sudo_password="secret")
        cmd, stdin = c._prepare_command("cat /etc/sudoers")
        assert cmd == "cat /etc/sudoers"
        assert stdin is None

    def test_sudo_password_takes_priority_over_ssh_password(self):
        """sudo_password is used, not the SSH password."""
        c = SSHConnector(host="10.0.0.1", password="ssh_pass", sudo_password="sudo_pass")
        cmd, stdin = c._prepare_command("sudo docker ps")
        assert stdin == "sudo_pass\n"


class TestShellSafetyClassifySudo:
    """Tests for sudo classification: sudo is stripped, risk based on underlying command."""

    def test_sudo_read_command_is_read(self):
        """sudo + read-only → strip sudo → READ."""
        assert ShellSafety.classify("sudo docker ps") is CommandType.READ

    def test_sudo_read_with_flags_is_read(self):
        assert ShellSafety.classify("sudo -u admin docker ps") is CommandType.READ

    def test_sudo_dangerous_stays_dangerous(self):
        assert ShellSafety.classify("sudo rm -rf /tmp/x") is CommandType.DANGEROUS
        assert ShellSafety.classify("sudo systemctl restart nginx") is CommandType.DANGEROUS

    def test_sudo_write_stays_write(self):
        assert ShellSafety.classify("sudo docker restart web") is CommandType.WRITE

    def test_sudo_local_read_is_read(self):
        """sudo on local + read-only → strip sudo → READ (no longer blocked)."""
        assert ShellSafety.classify("sudo docker ps", local=True) is CommandType.READ

    def test_compound_sudo_read_is_read(self):
        assert ShellSafety.classify("sudo docker ps && sudo docker images") is CommandType.READ

    def test_compound_with_sudo_dangerous(self):
        assert (
            ShellSafety.classify("echo hi && sudo systemctl restart nginx") is CommandType.DANGEROUS
        )

    def test_su_remote_is_dangerous(self):
        assert ShellSafety.classify("su - root") is CommandType.DANGEROUS

    def test_sudo_cat_is_read(self):
        """sudo + cat → strip sudo → cat → READ."""
        assert ShellSafety.classify("sudo cat /var/log/syslog") is CommandType.READ

    def test_sudo_systemctl_restart_is_dangerous(self):
        """sudo + systemctl restart → strip sudo → DANGEROUS."""
        assert ShellSafety.classify("sudo systemctl restart nginx") is CommandType.DANGEROUS

    def test_sudo_local_cat_is_read(self):
        """sudo + cat on local → READ (no longer blocked)."""
        assert ShellSafety.classify("sudo cat /etc/hosts", local=True) is CommandType.READ

    def test_sudo_local_rm_rf_is_dangerous(self):
        """sudo + rm -rf on local → strip sudo → DANGEROUS."""
        assert ShellSafety.classify("sudo rm -rf /tmp/cache", local=True) is CommandType.DANGEROUS

    def test_sudo_su_is_dangerous(self):
        """sudo su → strip sudo → su → DANGEROUS."""
        assert ShellSafety.classify("sudo su - root") is CommandType.DANGEROUS


class TestGetSudoPassword:
    """Tests for ServerService.get_sudo_password() priority logic."""

    def _make_crypto(self) -> CryptoService:
        import base64

        key = base64.b64encode(b"0" * 32).decode()
        return CryptoService(key=key)

    def _make_server(
        self,
        crypto: CryptoService,
        password: str | None = None,
        sudo_password: str | None = None,
        use_ssh_password_for_sudo: bool = False,
    ) -> MagicMock:
        server = MagicMock()
        server.encrypted_password = crypto.encrypt(password) if password else None
        server.encrypted_sudo_password = crypto.encrypt(sudo_password) if sudo_password else None
        server.use_ssh_password_for_sudo = use_ssh_password_for_sudo
        return server

    def test_dedicated_sudo_password_takes_priority(self):
        crypto = self._make_crypto()
        server = self._make_server(
            crypto, password="ssh_pw", sudo_password="sudo_pw", use_ssh_password_for_sudo=True
        )
        service = ServerService(session=MagicMock(), crypto=crypto)
        assert service.get_sudo_password(server) == "sudo_pw"

    def test_ssh_password_fallback_when_enabled(self):
        crypto = self._make_crypto()
        server = self._make_server(crypto, password="ssh_pw", use_ssh_password_for_sudo=True)
        service = ServerService(session=MagicMock(), crypto=crypto)
        assert service.get_sudo_password(server) == "ssh_pw"

    def test_returns_none_when_fallback_disabled(self):
        crypto = self._make_crypto()
        server = self._make_server(crypto, password="ssh_pw", use_ssh_password_for_sudo=False)
        service = ServerService(session=MagicMock(), crypto=crypto)
        assert service.get_sudo_password(server) is None

    def test_returns_none_when_no_passwords(self):
        crypto = self._make_crypto()
        server = self._make_server(crypto)
        service = ServerService(session=MagicMock(), crypto=crypto)
        assert service.get_sudo_password(server) is None


class TestExecuteSudoWithPassword:
    """Tests for SSHConnector.execute() with sudo password injection via asyncssh."""

    @pytest.mark.asyncio
    async def test_execute_sudo_docker_ps_injects_password_via_stdin(self):
        """Full execute() flow: sudo docker ps with password → sudo -S -p '' + stdin."""
        connector = SSHConnector(
            host="10.200.100.85",
            username="admin",
            password="OJ#6QB0&6w4Q",
            sudo_password="OJ#6QB0&6w4Q",
        )

        mock_result = MagicMock()
        mock_result.exit_status = 0
        mock_result.stdout = "CONTAINER ID   IMAGE   COMMAND   STATUS\n"
        mock_result.stderr = ""

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch("asyncssh.connect", return_value=mock_conn):
            result = await connector.execute("sudo docker ps")

        assert result.exit_code == 0
        assert "CONTAINER ID" in result.stdout

        # Verify the command was called with sudo -S -p and password on stdin
        # (quotes get shell-escaped by _wrap_command, so check for "sudo -S -p")
        call_args = mock_conn.run.call_args
        wrapped_cmd = call_args[0][0]
        assert "sudo -S -p" in wrapped_cmd
        assert "docker ps" in wrapped_cmd
        assert call_args[1]["input"] == "OJ#6QB0&6w4Q\n"

    @pytest.mark.asyncio
    async def test_execute_sudo_without_password_uses_sudo_n(self):
        """Without password → sudo -n, fails fast."""
        connector = SSHConnector(host="10.200.100.85", username="admin", password="some_pw")

        mock_result = MagicMock()
        mock_result.exit_status = 1
        mock_result.stdout = ""
        mock_result.stderr = "sudo: a password is required\n"

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        with patch("asyncssh.connect", return_value=mock_conn):
            result = await connector.execute("sudo docker ps")

        assert result.exit_code == 1
        assert "password is required" in result.stderr

        call_args = mock_conn.run.call_args
        wrapped_cmd = call_args[0][0]
        assert "sudo -n" in wrapped_cmd
        assert call_args[1]["input"] is None
