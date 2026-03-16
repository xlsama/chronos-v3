import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Infrastructure, Service
from src.lib.logger import logger
from src.tools.exec_tools import get_connector


class ServiceCatalog:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        infrastructure_id: uuid.UUID,
        name: str,
        service_type: str,
        port: int | None = None,
        namespace: str | None = None,
        config_json: str | None = None,
        discovery_method: str = "manual",
    ) -> Service:
        svc = Service(
            infrastructure_id=infrastructure_id,
            name=name,
            service_type=service_type,
            port=port,
            namespace=namespace,
            config_json=config_json,
            discovery_method=discovery_method,
        )
        self.session.add(svc)
        await self.session.commit()
        await self.session.refresh(svc)
        return svc

    async def list_by_infra(self, infrastructure_id: uuid.UUID) -> list[Service]:
        result = await self.session.execute(
            select(Service)
            .where(Service.infrastructure_id == infrastructure_id)
            .order_by(Service.name)
        )
        return list(result.scalars().all())

    async def get(self, service_id: uuid.UUID) -> Service | None:
        return await self.session.get(Service, service_id)

    async def delete(self, service_id: uuid.UUID) -> bool:
        svc = await self.session.get(Service, service_id)
        if not svc:
            return False
        await self.session.delete(svc)
        await self.session.commit()
        return True

    async def auto_discover(self, infrastructure_id: uuid.UUID) -> list[Service]:
        """Auto-discover services running on the infrastructure."""
        infra = await self.session.get(Infrastructure, infrastructure_id)
        if not infra:
            raise ValueError(f"Infrastructure not found: {infrastructure_id}")

        connector = await get_connector(str(infrastructure_id))
        discovered: list[Service] = []

        if infra.type == "kubernetes":
            discovered.extend(await self._discover_k8s(infrastructure_id, connector))
        else:
            discovered.extend(await self._discover_ssh(infrastructure_id, connector))

        return discovered

    async def _discover_ssh(self, infra_id: uuid.UUID, connector) -> list[Service]:
        """Discover services via SSH commands."""
        discovered: list[Service] = []

        # Docker containers
        try:
            result = await connector.execute(
                "docker ps --format '{{.Names}}\\t{{.Ports}}\\t{{.Image}}' 2>/dev/null"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 1:
                        name = parts[0].strip()
                        port = self._extract_port(parts[1]) if len(parts) > 1 else None
                        svc = await self._create_if_not_exists(
                            infra_id, name, "docker", port
                        )
                        if svc:
                            discovered.append(svc)
        except Exception as e:
            logger.debug(f"Docker discovery failed: {e}")

        # Systemd services (active)
        try:
            result = await connector.execute(
                "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split()
                    if parts:
                        unit_name = parts[0].replace(".service", "")
                        # Skip system services
                        if self._is_interesting_service(unit_name):
                            svc = await self._create_if_not_exists(
                                infra_id, unit_name, "systemd"
                            )
                            if svc:
                                discovered.append(svc)
        except Exception as e:
            logger.debug(f"Systemd discovery failed: {e}")

        # Listening ports
        try:
            result = await connector.execute("ss -tlnp 2>/dev/null")
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                    match = re.search(r":(\d+)\s", line)
                    proc_match = re.search(r'users:\(\("([^"]+)"', line)
                    if match and proc_match:
                        port = int(match.group(1))
                        proc_name = proc_match.group(1)
                        svc_type = self._guess_service_type(proc_name, port)
                        svc = await self._create_if_not_exists(
                            infra_id, proc_name, svc_type, port
                        )
                        if svc:
                            discovered.append(svc)
        except Exception as e:
            logger.debug(f"Port discovery failed: {e}")

        # Cron jobs
        try:
            result = await connector.execute("crontab -l 2>/dev/null")
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Extract script name from cron entry
                        parts = line.split()
                        if len(parts) > 5:
                            cmd = " ".join(parts[5:])
                            name = cmd.split("/")[-1].split()[0][:50]
                            svc = await self._create_if_not_exists(
                                infra_id, f"cron-{name}", "cron_job"
                            )
                            if svc:
                                discovered.append(svc)
        except Exception as e:
            logger.debug(f"Cron discovery failed: {e}")

        return discovered

    async def _discover_k8s(self, infra_id: uuid.UUID, connector) -> list[Service]:
        """Discover services in Kubernetes."""
        discovered: list[Service] = []

        # Deployments
        try:
            result = await connector.execute(
                "kubectl get deployments --all-namespaces -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name --no-headers"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 2:
                        ns, name = parts[0], parts[1]
                        svc = await self._create_if_not_exists(
                            infra_id, name, "k8s_deployment", namespace=ns
                        )
                        if svc:
                            discovered.append(svc)
        except Exception as e:
            logger.debug(f"K8s deployment discovery failed: {e}")

        # StatefulSets
        try:
            result = await connector.execute(
                "kubectl get statefulsets --all-namespaces -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name --no-headers"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 2:
                        ns, name = parts[0], parts[1]
                        svc = await self._create_if_not_exists(
                            infra_id, name, "k8s_statefulset", namespace=ns
                        )
                        if svc:
                            discovered.append(svc)
        except Exception as e:
            logger.debug(f"K8s statefulset discovery failed: {e}")

        # K8s Services (to get ports)
        try:
            result = await connector.execute(
                "kubectl get services --all-namespaces -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PORT:.spec.ports[0].port --no-headers"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] != "kubernetes":
                        ns, name = parts[0], parts[1]
                        port = int(parts[2]) if parts[2] != "<none>" else None
                        svc = await self._create_if_not_exists(
                            infra_id, f"svc-{name}", "k8s_service", port=port, namespace=ns
                        )
                        if svc:
                            discovered.append(svc)
        except Exception as e:
            logger.debug(f"K8s service discovery failed: {e}")

        return discovered

    async def _create_if_not_exists(
        self,
        infra_id: uuid.UUID,
        name: str,
        service_type: str,
        port: int | None = None,
        namespace: str | None = None,
    ) -> Service | None:
        """Create service if it doesn't already exist for this infra."""
        result = await self.session.execute(
            select(Service).where(
                Service.infrastructure_id == infra_id,
                Service.name == name,
            )
        )
        if result.scalar_one_or_none():
            return None

        svc = Service(
            infrastructure_id=infra_id,
            name=name,
            service_type=service_type,
            port=port,
            namespace=namespace,
            discovery_method="auto_discovered",
        )
        self.session.add(svc)
        await self.session.flush()
        return svc

    @staticmethod
    def _extract_port(ports_str: str) -> int | None:
        match = re.search(r"(\d+)->", ports_str)
        if match:
            return int(match.group(1))
        match = re.search(r":(\d+)", ports_str)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _is_interesting_service(name: str) -> bool:
        """Filter out common system services."""
        skip = {
            "systemd", "dbus", "rsyslog", "cron", "ssh", "sshd",
            "networkd", "resolved", "timesyncd", "udev", "polkit",
            "snapd", "unattended-upgrades", "accounts-daemon",
            "udisks2", "ModemManager", "NetworkManager",
        }
        return name not in skip

    @staticmethod
    def _guess_service_type(proc_name: str, port: int) -> str:
        db_ports = {3306: "database", 5432: "database", 27017: "database"}
        cache_ports = {6379: "cache", 11211: "cache"}
        queue_ports = {5672: "queue", 9092: "queue"}

        if port in db_ports:
            return db_ports[port]
        if port in cache_ports:
            return cache_ports[port]
        if port in queue_ports:
            return queue_ports[port]
        return "process"
