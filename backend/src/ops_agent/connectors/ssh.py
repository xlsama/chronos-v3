import asyncio
import io
from dataclasses import dataclass

import paramiko

from src.lib.logger import logger


@dataclass
class SSHResult:
    exit_code: int
    stdout: str
    stderr: str


class SSHConnector:
    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        private_key: str | None = None,
        timeout: int = 30,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.timeout = timeout

    def _create_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": self.timeout,
        }

        if self.private_key:
            key = paramiko.RSAKey.from_private_key(io.StringIO(self.private_key))
            connect_kwargs["pkey"] = key
        elif self.password:
            connect_kwargs["password"] = self.password

        client.connect(**connect_kwargs)
        return client

    def _run_command(self, command: str) -> SSHResult:
        client = self._create_client()
        try:
            _stdin, stdout, stderr = client.exec_command(command, timeout=self.timeout)
            exit_code = stdout.channel.recv_exit_status()
            return SSHResult(
                exit_code=exit_code,
                stdout=stdout.read().decode(),
                stderr=stderr.read().decode(),
            )
        finally:
            client.close()

    async def execute(self, command: str) -> SSHResult:
        logger.info(f"SSH executing on {self.host}: {command}")
        return await asyncio.to_thread(self._run_command, command)

    async def test_connection(self) -> bool:
        try:
            result = await self.execute("echo ok")
            return result.exit_code == 0
        except Exception as e:
            logger.warning(f"SSH connection test failed for {self.host}: {e}")
            return False
