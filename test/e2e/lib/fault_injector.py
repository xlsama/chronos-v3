from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import asyncssh


@dataclass
class FaultInjector:
    host: str = "localhost"
    port: int = 12222
    username: str = "root"
    password: str = "testpassword"

    async def _exec(self, cmd: str) -> tuple[str, str, int]:
        async with asyncssh.connect(
            self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            known_hosts=None,
        ) as conn:
            result = await conn.run(cmd, check=False)
            return (
                result.stdout or "",
                result.stderr or "",
                result.returncode if result.returncode is not None else 0,
            )

    def exec(self, cmd: str) -> tuple[str, str, int]:
        return asyncio.run(self._exec(cmd))

    def inject_disk_full(self) -> None:
        self.exec("fallocate -l 450M /tmp/testfill")

    def kill_process(self, name: str) -> None:
        self.exec(f'pkill -f "{name}"')

    def is_process_running(self, name: str) -> bool:
        _, _, code = self.exec(f'pgrep -f "{name}"')
        return code == 0
