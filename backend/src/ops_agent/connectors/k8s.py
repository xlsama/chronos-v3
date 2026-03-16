import asyncio
import tempfile
from dataclasses import dataclass

from src.lib.logger import logger


@dataclass
class K8sResult:
    exit_code: int
    stdout: str
    stderr: str


class K8sConnector:
    def __init__(
        self,
        kubeconfig: str,
        context: str | None = None,
        namespace: str = "default",
        timeout: int = 30,
    ):
        self.kubeconfig = kubeconfig
        self.context = context
        self.namespace = namespace
        self.timeout = timeout

    def _run_command(self, command: str) -> K8sResult:
        """Run a kubectl-style command by translating to kubernetes API calls.

        For simplicity, we write kubeconfig to a temp file and invoke kubectl subprocess.
        This avoids complex API mapping and supports all kubectl commands naturally.
        """
        import subprocess

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kubeconfig", delete=True) as f:
            f.write(self.kubeconfig)
            f.flush()

            # Build kubectl command with kubeconfig
            env_cmd = f"KUBECONFIG={f.name}"
            if self.context:
                env_cmd += f" kubectl --context={self.context}"
            else:
                env_cmd += " kubectl"

            # If the command starts with "kubectl", strip it
            actual_cmd = command
            if actual_cmd.startswith("kubectl "):
                actual_cmd = actual_cmd[len("kubectl "):]

            # Add default namespace if not specified in command
            if "-n " not in actual_cmd and "--namespace" not in actual_cmd and "--all-namespaces" not in actual_cmd:
                full_cmd = f"{env_cmd} -n {self.namespace} {actual_cmd}"
            else:
                full_cmd = f"{env_cmd} {actual_cmd}"

            try:
                result = subprocess.run(
                    full_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                return K8sResult(
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
            except subprocess.TimeoutExpired:
                return K8sResult(exit_code=1, stdout="", stderr="Command timed out")

    async def execute(self, command: str) -> K8sResult:
        logger.info(f"K8s executing: {command}")
        return await asyncio.to_thread(self._run_command, command)

    async def test_connection(self) -> bool:
        try:
            result = await self.execute("kubectl cluster-info")
            return result.exit_code == 0
        except Exception as e:
            logger.warning(f"K8s connection test failed: {e}")
            return False
