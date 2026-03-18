from __future__ import annotations

import subprocess
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parents[1]


class TestInfra:
    def __init__(self, case_name: str) -> None:
        self.compose_file = str(E2E_DIR / case_name / "docker-compose.yml")
        self.project_name = f"chronos-e2e-{case_name}"

    def start(self) -> None:
        print(f"[infra] Starting {self.project_name}...")
        subprocess.run(
            ["docker", "compose", "-f", self.compose_file, "-p", self.project_name, "up", "-d", "--wait"],
            check=True,
            timeout=180,
        )
        print(f"[infra] {self.project_name} is up")

    def stop(self) -> None:
        print(f"[infra] Stopping {self.project_name}...")
        try:
            subprocess.run(
                ["docker", "compose", "-f", self.compose_file, "-p", self.project_name, "down", "-v", "--remove-orphans"],
                check=True,
                timeout=60,
            )
        except Exception as e:
            print(f"[infra] Warning during stop: {e}")
