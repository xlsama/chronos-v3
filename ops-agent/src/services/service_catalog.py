import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Connection, Service
from src.lib.logger import logger
from src.tools.exec_tools import get_connector


class ServiceCatalog:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        connection_id: uuid.UUID,
        name: str,
        port: int | None = None,
        namespace: str | None = None,
        discovery_method: str = "manual",
    ) -> Service:
        svc = Service(
            connection_id=connection_id,
            name=name,
            port=port,
            namespace=namespace,
            discovery_method=discovery_method,
        )
        self.session.add(svc)
        await self.session.commit()
        await self.session.refresh(svc)
        return svc

    async def list_by_connection(self, connection_id: uuid.UUID) -> list[Service]:
        result = await self.session.execute(
            select(Service)
            .where(Service.connection_id == connection_id)
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

    async def auto_discover(self, connection_id: uuid.UUID) -> list[Service]:
        """Auto-discover services running on the connection."""
        conn = await self.session.get(Connection, connection_id)
        if not conn:
            raise ValueError(f"Connection not found: {connection_id}")

        connector = await get_connector(str(connection_id))
        discovered: list[Service] = []

        if conn.type == "kubernetes":
            discovered.extend(await self._discover_k8s(connection_id, connector))
        else:
            discovered.extend(await self._discover_ssh(connection_id, connector))

        return discovered

    async def _discover_ssh(self, conn_id: uuid.UUID, connector) -> list[Service]:
        """Discover services via SSH commands."""
        discovered: list[Service] = []

        # Docker containers
        try:
            result = await connector.execute(
                "docker ps --format '{{.Names}}\\t{{.Ports}}' 2>/dev/null"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 1:
                        name = parts[0].strip()
                        port = self._extract_port(parts[1]) if len(parts) > 1 else None
                        svc = await self._create_if_not_exists(
                            conn_id, name, port
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
                                conn_id, unit_name
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
                        svc = await self._create_if_not_exists(
                            conn_id, proc_name, port
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
                                conn_id, f"cron-{name}"
                            )
                            if svc:
                                discovered.append(svc)
        except Exception as e:
            logger.debug(f"Cron discovery failed: {e}")

        return discovered

    async def _discover_k8s(self, conn_id: uuid.UUID, connector) -> list[Service]:
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
                            conn_id, name, namespace=ns
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
                            conn_id, name, namespace=ns
                        )
                        if svc:
                            discovered.append(svc)
        except Exception as e:
            logger.debug(f"K8s statefulset discovery failed: {e}")

        return discovered

    async def _create_if_not_exists(
        self,
        conn_id: uuid.UUID,
        name: str,
        port: int | None = None,
        namespace: str | None = None,
    ) -> Service | None:
        """Create service if it doesn't already exist for this connection."""
        result = await self.session.execute(
            select(Service).where(
                Service.connection_id == conn_id,
                Service.name == name,
            )
        )
        if result.scalar_one_or_none():
            return None

        svc = Service(
            connection_id=conn_id,
            name=name,
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
