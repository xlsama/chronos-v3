import asyncio
from dataclasses import dataclass

import asyncssh

from src.lib.logger import get_logger

log = get_logger(component="ssh")


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
        bastion_host: str | None = None,
        bastion_port: int | None = None,
        bastion_username: str | None = None,
        bastion_password: str | None = None,
        bastion_private_key: str | None = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.timeout = timeout
        self.bastion_host = bastion_host
        self.bastion_port = bastion_port or 22
        self.bastion_username = bastion_username
        self.bastion_password = bastion_password
        self.bastion_private_key = bastion_private_key

    @staticmethod
    def _build_connect_opts(
        host: str,
        port: int,
        username: str,
        password: str | None = None,
        private_key: str | None = None,
    ) -> dict:
        opts: dict = {
            "host": host,
            "port": port,
            "username": username,
            "known_hosts": None,
        }
        if private_key:
            key = asyncssh.import_private_key(private_key)
            opts["client_keys"] = [key]
        elif password:
            opts["password"] = password
        return opts

    async def execute(self, command: str) -> SSHResult:
        log.info("Executing", host=self.host, command=command)

        async def _run() -> SSHResult:
            if self.bastion_host:
                log.info("Connecting via bastion", bastion_host=self.bastion_host, bastion_port=self.bastion_port, target_host=self.host, target_port=self.port)
                bastion_opts = self._build_connect_opts(
                    host=self.bastion_host,
                    port=self.bastion_port,
                    username=self.bastion_username or self.username,
                    password=self.bastion_password,
                    private_key=self.bastion_private_key,
                )
                target_opts = self._build_connect_opts(
                    host=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    private_key=self.private_key,
                )
                # Remove host/port from target_opts as they're passed to connect_ssh
                target_host = target_opts.pop("host")
                target_port = target_opts.pop("port")

                async with asyncssh.connect(**bastion_opts) as tunnel:
                    async with tunnel.connect_ssh(
                        target_host, target_port, **target_opts
                    ) as conn:
                        result = await conn.run(command)
                        return SSHResult(
                            exit_code=result.exit_status or 0,
                            stdout=result.stdout or "",
                            stderr=result.stderr or "",
                        )
            else:
                log.info("Direct connect", host=self.host, port=self.port)
                target_opts = self._build_connect_opts(
                    host=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    private_key=self.private_key,
                )
                async with asyncssh.connect(**target_opts) as conn:
                    result = await conn.run(command)
                    return SSHResult(
                        exit_code=result.exit_status or 0,
                        stdout=result.stdout or "",
                        stderr=result.stderr or "",
                    )

        return await asyncio.wait_for(_run(), timeout=self.timeout)

    async def test_connection(self) -> bool:
        try:
            result = await self.execute("echo ok")
            return result.exit_code == 0
        except Exception as e:
            log.warning("SSH connection test failed", host=self.host, error=str(e))
            return False
