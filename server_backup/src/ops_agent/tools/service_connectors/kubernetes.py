import asyncio
import os
import tempfile

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult

log = get_logger(component="service_exec")


class KubernetesConnector(ServiceConnector):
    service_type = "kubernetes"

    def __init__(
        self,
        host: str,
        port: int,
        kubeconfig: str,
        default_namespace: str = "default",
        context: str | None = None,
    ):
        self._host = host
        self._port = port
        self._kubeconfig_content = kubeconfig
        self._default_namespace = default_namespace
        self._context = context
        self._kubeconfig_path: str | None = None

    def _ensure_kubeconfig(self) -> str:
        """Write kubeconfig to a temp file (once, reused across executions)."""
        if self._kubeconfig_path and os.path.exists(self._kubeconfig_path):
            return self._kubeconfig_path

        fd, path = tempfile.mkstemp(prefix="chronos_kube_", suffix=".yaml")
        try:
            os.write(fd, self._kubeconfig_content.encode())
        finally:
            os.close(fd)
        os.chmod(path, 0o600)
        self._kubeconfig_path = path
        log.info("Kubeconfig written", path=path, host=self._host)
        return path

    # Cluster-scoped resource prefixes — skip namespace injection for these
    _CLUSTER_SCOPED_PREFIXES = (
        "get nodes",
        "get node",
        "describe node",
        "top node",
        "top nodes",
        "get namespaces",
        "get namespace",
        "get ns",
        "get clusterrole",
        "get clusterrolebinding",
        "get pv ",
        "get pv\n",
        "get persistentvolume",
        "get storageclass",
        "get sc ",
        "get ingressclass",
        "api-resources",
        "api-versions",
        "cluster-info",
        "version",
    )

    def _wrap_command(self, command: str) -> str:
        """Prepend namespace and context flags if not already present."""
        cmd = command.strip()

        # Extract the part after "kubectl "
        if cmd.startswith("kubectl "):
            rest = cmd[len("kubectl ") :]
        else:
            return cmd

        # Check if cluster-scoped
        is_cluster_scoped = any(rest.startswith(p) for p in self._CLUSTER_SCOPED_PREFIXES)

        flags: list[str] = []

        if self._context and "--context" not in cmd:
            flags.append(f"--context={self._context}")

        if (
            not is_cluster_scoped
            and "-n " not in cmd
            and "--namespace" not in cmd
            and "--all-namespaces" not in cmd
            and " -A" not in cmd
        ):
            flags.append(f"-n {self._default_namespace}")

        if flags:
            cmd = "kubectl " + " ".join(flags) + " " + rest

        return cmd

    async def execute(self, command: str) -> ServiceResult:
        cmd = command.strip()

        if not cmd.startswith("kubectl"):
            return ServiceResult(
                success=False,
                output="",
                error="命令必须以 kubectl 开头。示例: kubectl get pods",
            )

        cmd = self._wrap_command(cmd)
        env = os.environ.copy()
        env["KUBECONFIG"] = self._ensure_kubeconfig()

        log.info("Executing kubectl", command_len=len(cmd), host=self._host)
        log.debug("kubectl command", command=cmd)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await proc.communicate()
        except OSError as e:
            return ServiceResult(success=False, output="", error=f"kubectl 执行失败: {e}")

        stdout_str = stdout.decode(errors="replace").strip()
        stderr_str = stderr.decode(errors="replace").strip()

        if proc.returncode != 0:
            error_msg = stderr_str or f"kubectl exited with code {proc.returncode}"
            log.info("kubectl error", exit_code=proc.returncode, error_len=len(error_msg))
            return ServiceResult(
                success=False,
                output=stdout_str,
                error=error_msg,
            )

        # Merge stderr warnings into output
        output = stdout_str
        if stderr_str and stdout_str:
            output = f"{stderr_str}\n\n{stdout_str}"
        elif stderr_str:
            output = stderr_str

        log.info("kubectl result", output_len=len(output))
        return ServiceResult(success=True, output=output or "(no output)")

    async def close(self) -> None:
        if self._kubeconfig_path and os.path.exists(self._kubeconfig_path):
            try:
                os.unlink(self._kubeconfig_path)
                log.info("Kubeconfig cleaned up", path=self._kubeconfig_path)
            except OSError:
                pass
            self._kubeconfig_path = None
