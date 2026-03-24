import asyncio
import json
import os
import shlex
import tempfile

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult

log = get_logger(component="service_exec")


class DockerConnector(ServiceConnector):
    service_type = "docker"

    def __init__(
        self,
        host: str,
        port: int,
        use_tls: bool = False,
        tls_certs: str | None = None,
    ):
        self._host = host
        self._port = port
        self._use_tls = use_tls
        self._tls_certs = tls_certs  # JSON string: {"ca_cert", "client_cert", "client_key"}
        self._client = None
        self._tls_temp_files: list[str] = []

    def _get_client(self):
        if self._client is not None:
            return self._client

        import docker

        base_url = f"tcp://{self._host}:{self._port}"
        tls_config = None

        if self._use_tls and self._tls_certs:
            certs = json.loads(self._tls_certs)
            ca_path = self._write_temp_file(certs.get("ca_cert", ""), "ca.pem")
            cert_path = self._write_temp_file(certs.get("client_cert", ""), "cert.pem")
            key_path = self._write_temp_file(certs.get("client_key", ""), "key.pem")
            tls_config = docker.tls.TLSConfig(
                ca_cert=ca_path,
                client_cert=(cert_path, key_path),
            )

        log.info("Connecting to Docker", host=self._host, port=self._port, tls=self._use_tls)
        self._client = docker.DockerClient(base_url=base_url, tls=tls_config, timeout=10)
        return self._client

    def _write_temp_file(self, content: str, suffix: str) -> str:
        fd, path = tempfile.mkstemp(prefix="chronos_docker_", suffix=f"_{suffix}")
        try:
            os.write(fd, content.encode())
        finally:
            os.close(fd)
        os.chmod(path, 0o600)
        self._tls_temp_files.append(path)
        return path

    def _parse_command(self, command: str) -> tuple[str, list[str]]:
        """Parse docker CLI command into (subcommand, args)."""
        cmd = command.strip()
        if cmd.startswith("docker "):
            cmd = cmd[len("docker "):]
        elif cmd == "docker":
            return "version", []

        parts = shlex.split(cmd)
        if not parts:
            return "version", []

        return parts[0].lower(), parts[1:]

    def _execute_sync(self, command: str) -> ServiceResult:
        client = self._get_client()
        subcmd, args = self._parse_command(command)

        log.info("Executing docker", subcommand=subcmd, args_len=len(args))

        if subcmd == "ps":
            show_all = "-a" in args or "--all" in args
            containers = client.containers.list(all=show_all)
            if not containers:
                return ServiceResult(success=True, output="(no containers)")
            lines = ["CONTAINER ID | NAME | IMAGE | STATUS | PORTS"]
            lines.append("---|---|---|---|---")
            for c in containers:
                ports = ", ".join(
                    f"{v[0]['HostPort']}->{k}" if v else k
                    for k, v in (c.ports or {}).items()
                )
                lines.append(
                    f"{c.short_id} | {c.name} | {c.image.tags[0] if c.image.tags else c.image.short_id} | {c.status} | {ports}"
                )
            lines.append(f"\n({len(containers)} containers)")
            return ServiceResult(success=True, output="\n".join(lines))

        elif subcmd == "inspect":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker inspect <容器名>")
            container = client.containers.get(args[0])
            output = json.dumps(container.attrs, indent=2, ensure_ascii=False, default=str)
            return ServiceResult(success=True, output=output)

        elif subcmd == "logs":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker logs <容器名>")
            name = args[0]
            tail = "200"
            for i, a in enumerate(args[1:], 1):
                if a == "--tail" and i + 1 < len(args):
                    tail = args[i + 1]
                elif a.startswith("--tail="):
                    tail = a.split("=", 1)[1]
            container = client.containers.get(name)
            logs = container.logs(tail=int(tail) if tail != "all" else "all").decode(
                errors="replace"
            )
            return ServiceResult(success=True, output=logs or "(no logs)")

        elif subcmd == "restart":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker restart <容器名>")
            container = client.containers.get(args[0])
            container.restart()
            return ServiceResult(success=True, output=f"容器 {args[0]} 已重启")

        elif subcmd == "stop":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker stop <容器名>")
            container = client.containers.get(args[0])
            container.stop()
            return ServiceResult(success=True, output=f"容器 {args[0]} 已停止")

        elif subcmd == "start":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker start <容器名>")
            container = client.containers.get(args[0])
            container.start()
            return ServiceResult(success=True, output=f"容器 {args[0]} 已启动")

        elif subcmd == "exec":
            if len(args) < 2:
                return ServiceResult(
                    success=False, output="", error="用法: docker exec <容器名> <命令>"
                )
            container = client.containers.get(args[0])
            exec_cmd = " ".join(args[1:])
            result = container.exec_run(exec_cmd)
            output = result.output.decode(errors="replace") if result.output else ""
            if result.exit_code != 0:
                return ServiceResult(
                    success=False, output=output, error=f"exit code {result.exit_code}"
                )
            return ServiceResult(success=True, output=output or "(no output)")

        elif subcmd == "top":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker top <容器名>")
            container = client.containers.get(args[0])
            top = container.top()
            titles = top.get("Titles", [])
            procs = top.get("Processes", [])
            if not titles:
                return ServiceResult(success=True, output="(no processes)")
            lines = [" | ".join(titles)]
            lines.append(" | ".join("---" for _ in titles))
            for proc in procs:
                lines.append(" | ".join(proc))
            return ServiceResult(success=True, output="\n".join(lines))

        elif subcmd == "stats":
            containers = client.containers.list()
            if not containers:
                return ServiceResult(success=True, output="(no running containers)")
            lines = ["CONTAINER | NAME | CPU % | MEM USAGE | MEM %"]
            lines.append("---|---|---|---|---")
            for c in containers:
                try:
                    stats = c.stats(stream=False)
                    cpu = self._calc_cpu_percent(stats)
                    mem_usage = stats["memory_stats"].get("usage", 0)
                    mem_limit = stats["memory_stats"].get("limit", 1)
                    mem_pct = (mem_usage / mem_limit * 100) if mem_limit else 0
                    mem_str = self._format_bytes(mem_usage)
                    lines.append(
                        f"{c.short_id} | {c.name} | {cpu:.1f}% | {mem_str} | {mem_pct:.1f}%"
                    )
                except Exception:
                    lines.append(f"{c.short_id} | {c.name} | - | - | -")
            return ServiceResult(success=True, output="\n".join(lines))

        elif subcmd == "images":
            images = client.images.list()
            if not images:
                return ServiceResult(success=True, output="(no images)")
            lines = ["REPOSITORY:TAG | IMAGE ID | SIZE"]
            lines.append("---|---|---")
            for img in images:
                tag = img.tags[0] if img.tags else "<none>"
                size = self._format_bytes(img.attrs.get("Size", 0))
                lines.append(f"{tag} | {img.short_id} | {size}")
            lines.append(f"\n({len(images)} images)")
            return ServiceResult(success=True, output="\n".join(lines))

        elif subcmd == "pull":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker pull <镜像名>")
            image = client.images.pull(args[0])
            tag = image.tags[0] if image.tags else image.short_id
            return ServiceResult(success=True, output=f"已拉取镜像: {tag}")

        elif subcmd == "rm":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker rm <容器名>")
            force = "-f" in args or "--force" in args
            name = [a for a in args if not a.startswith("-")][0]
            container = client.containers.get(name)
            container.remove(force=force)
            return ServiceResult(success=True, output=f"容器 {name} 已删除")

        elif subcmd == "kill":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker kill <容器名>")
            container = client.containers.get(args[0])
            container.kill()
            return ServiceResult(success=True, output=f"容器 {args[0]} 已强制停止")

        elif subcmd in ("pause", "unpause"):
            if not args:
                return ServiceResult(
                    success=False, output="", error=f"用法: docker {subcmd} <容器名>"
                )
            container = client.containers.get(args[0])
            if subcmd == "pause":
                container.pause()
            else:
                container.unpause()
            action = "已暂停" if subcmd == "pause" else "已恢复"
            return ServiceResult(success=True, output=f"容器 {args[0]} {action}")

        elif subcmd == "diff":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker diff <容器名>")
            container = client.containers.get(args[0])
            diff = container.diff()
            if not diff:
                return ServiceResult(success=True, output="(no changes)")
            kind_map = {0: "C", 1: "A", 2: "D"}
            lines = [f"{kind_map.get(d['Kind'], '?')} {d['Path']}" for d in diff]
            return ServiceResult(success=True, output="\n".join(lines))

        elif subcmd == "version":
            info = client.version()
            lines = [
                f"Server Version: {info.get('Version', 'unknown')}",
                f"API Version: {info.get('ApiVersion', 'unknown')}",
                f"OS/Arch: {info.get('Os', '')}/{info.get('Arch', '')}",
                f"Go Version: {info.get('GoVersion', 'unknown')}",
            ]
            return ServiceResult(success=True, output="\n".join(lines))

        elif subcmd == "info":
            info = client.info()
            lines = [
                f"Containers: {info.get('Containers', 0)} "
                f"(Running: {info.get('ContainersRunning', 0)}, "
                f"Stopped: {info.get('ContainersStopped', 0)})",
                f"Images: {info.get('Images', 0)}",
                f"Server Version: {info.get('ServerVersion', 'unknown')}",
                f"OS: {info.get('OperatingSystem', 'unknown')}",
                f"Architecture: {info.get('Architecture', 'unknown')}",
                f"CPUs: {info.get('NCPU', 'unknown')}",
                f"Memory: {self._format_bytes(info.get('MemTotal', 0))}",
            ]
            return ServiceResult(success=True, output="\n".join(lines))

        elif subcmd == "rmi":
            if not args:
                return ServiceResult(success=False, output="", error="用法: docker rmi <镜像名>")
            force = "-f" in args or "--force" in args
            name = [a for a in args if not a.startswith("-")][0]
            client.images.remove(name, force=force)
            return ServiceResult(success=True, output=f"镜像 {name} 已删除")

        elif subcmd == "prune":
            result_containers = client.containers.prune()
            result_images = client.images.prune()
            deleted_containers = len(result_containers.get("ContainersDeleted", []) or [])
            deleted_images = len(result_images.get("ImagesDeleted", []) or [])
            reclaimed = (
                result_containers.get("SpaceReclaimed", 0)
                + result_images.get("SpaceReclaimed", 0)
            )
            return ServiceResult(
                success=True,
                output=f"清理完成: 删除 {deleted_containers} 个容器, "
                f"{deleted_images} 个镜像, 回收 {self._format_bytes(reclaimed)}",
            )

        else:
            return ServiceResult(
                success=False,
                output="",
                error=f"不支持的 docker 子命令: {subcmd}。"
                f"支持: ps, inspect, logs, restart, stop, start, exec, top, stats, "
                f"images, pull, rm, kill, pause, unpause, diff, version, info, rmi, prune",
            )

    async def execute(self, command: str) -> ServiceResult:
        try:
            return await asyncio.to_thread(self._execute_sync, command)
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                return ServiceResult(success=False, output="", error=f"容器或镜像不存在: {e}")
            raise

    async def close(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        for path in self._tls_temp_files:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass
        self._tls_temp_files.clear()

    @staticmethod
    def _calc_cpu_percent(stats: dict) -> float:
        cpu_delta = (
            stats["cpu_stats"]["cpu_usage"]["total_usage"]
            - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        )
        system_delta = (
            stats["cpu_stats"].get("system_cpu_usage", 0)
            - stats["precpu_stats"].get("system_cpu_usage", 0)
        )
        if system_delta > 0 and cpu_delta > 0:
            online_cpus = stats["cpu_stats"].get(
                "online_cpus", len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))
            )
            return (cpu_delta / system_delta) * online_cpus * 100.0
        return 0.0

    @staticmethod
    def _format_bytes(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(size) < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
