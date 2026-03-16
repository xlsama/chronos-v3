import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Connection, Project, Service, ServiceConnectionBinding
from src.lib.errors import ValidationError
from src.lib.logger import logger
from src.ops_agent.tools.exec_tools import get_connector


class ServiceCatalog:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        project_id: uuid.UUID,
        name: str,
        slug: str | None = None,
        service_type: str = "custom",
        description: str | None = None,
        business_context: str | None = None,
        owner: str | None = None,
        keywords: list[str] | None = None,
        status: str = "unknown",
        source: str = "manual",
        metadata: dict | None = None,
    ) -> Service:
        project = await self.session.get(Project, project_id)
        if not project:
            raise ValidationError("Project not found")

        resolved_slug = slug or self._generate_slug(name)
        existing = (
            await self.session.execute(
                select(Service).where(
                    Service.project_id == project_id,
                    Service.slug == resolved_slug,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise ValidationError("Service slug already exists in this project")

        svc = Service(
            project_id=project_id,
            name=name,
            slug=resolved_slug,
            service_type=service_type,
            description=description,
            business_context=business_context,
            owner=owner,
            keywords=keywords or [],
            status=status,
            source=source,
            service_metadata=metadata or {},
        )
        self.session.add(svc)
        await self.session.commit()
        await self.session.refresh(svc)
        return svc

    async def update(self, service: Service, **kwargs) -> Service:
        incoming_name = kwargs.get("name", service.name)
        incoming_slug = kwargs.get("slug") or self._generate_slug(incoming_name)
        duplicate = (
            await self.session.execute(
                select(Service).where(
                    Service.project_id == service.project_id,
                    Service.slug == incoming_slug,
                    Service.id != service.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate:
            raise ValidationError("Service slug already exists in this project")

        for key, value in kwargs.items():
            if value is None:
                continue
            if key == "metadata":
                service.service_metadata = value
            elif hasattr(service, key):
                setattr(service, key, value)
        service.slug = incoming_slug
        await self.session.commit()
        await self.session.refresh(service)
        return service

    async def list_by_project(self, project_id: uuid.UUID) -> list[Service]:
        result = await self.session.execute(
            select(Service)
            .where(Service.project_id == project_id)
            .order_by(Service.name)
        )
        return list(result.scalars().all())

    async def list_by_connection(self, connection_id: uuid.UUID) -> list[Service]:
        result = await self.session.execute(
            select(Service)
            .join(ServiceConnectionBinding, ServiceConnectionBinding.service_id == Service.id)
            .where(ServiceConnectionBinding.connection_id == connection_id)
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
        conn = await self.session.get(Connection, connection_id)
        if not conn:
            raise ValueError(f"Connection not found: {connection_id}")
        if not conn.project_id:
            raise ValueError("Connection must belong to a project before discovery")

        connector = await get_connector(str(connection_id))
        discovered: list[Service] = []

        if conn.type == "kubernetes":
            discovered.extend(await self._discover_k8s(conn, connector))
        else:
            discovered.extend(await self._discover_ssh(conn, connector))

        await self.session.flush()
        return discovered

    async def _discover_ssh(self, conn: Connection, connector) -> list[Service]:
        discovered: list[Service] = []

        try:
            result = await connector.execute("docker ps --format '{{.Names}}\\t{{.Ports}}' 2>/dev/null")
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    name = parts[0].strip()
                    port = self._extract_port(parts[1]) if len(parts) > 1 else None
                    svc = await self._create_or_bind_service(
                        conn,
                        name=name,
                        service_type="container",
                        metadata={"port": port} if port else {},
                    )
                    if svc:
                        discovered.append(svc)
        except Exception as exc:  # pragma: no cover - best effort discovery
            logger.debug(f"Docker discovery failed: {exc}")

        try:
            result = await connector.execute(
                "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split()
                    if parts:
                        unit_name = parts[0].replace(".service", "")
                        if self._is_interesting_service(unit_name):
                            svc = await self._create_or_bind_service(
                                conn,
                                name=unit_name,
                                service_type="system_service",
                            )
                            if svc:
                                discovered.append(svc)
        except Exception as exc:  # pragma: no cover - best effort discovery
            logger.debug(f"Systemd discovery failed: {exc}")

        try:
            result = await connector.execute("crontab -l 2>/dev/null")
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) > 5:
                            cmd = " ".join(parts[5:])
                            name = cmd.split("/")[-1].split()[0][:50]
                            svc = await self._create_or_bind_service(
                                conn,
                                name=f"cron-{name}",
                                service_type="cron_job",
                            )
                            if svc:
                                discovered.append(svc)
        except Exception as exc:  # pragma: no cover - best effort discovery
            logger.debug(f"Cron discovery failed: {exc}")

        return discovered

    async def _discover_k8s(self, conn: Connection, connector) -> list[Service]:
        discovered: list[Service] = []

        try:
            result = await connector.execute(
                "kubectl get deployments --all-namespaces -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name --no-headers"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 2:
                        namespace, name = parts[0], parts[1]
                        svc = await self._create_or_bind_service(
                            conn,
                            name=name,
                            service_type="k8s_deployment",
                            metadata={"namespace": namespace},
                        )
                        if svc:
                            discovered.append(svc)
        except Exception as exc:  # pragma: no cover - best effort discovery
            logger.debug(f"K8s deployment discovery failed: {exc}")

        try:
            result = await connector.execute(
                "kubectl get statefulsets --all-namespaces -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name --no-headers"
            )
            if result.exit_code == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 2:
                        namespace, name = parts[0], parts[1]
                        svc = await self._create_or_bind_service(
                            conn,
                            name=name,
                            service_type="k8s_statefulset",
                            metadata={"namespace": namespace},
                        )
                        if svc:
                            discovered.append(svc)
        except Exception as exc:  # pragma: no cover - best effort discovery
            logger.debug(f"K8s statefulset discovery failed: {exc}")

        return discovered

    async def _create_or_bind_service(
        self,
        conn: Connection,
        name: str,
        service_type: str,
        metadata: dict | None = None,
    ) -> Service | None:
        result = await self.session.execute(
            select(Service).where(
                Service.project_id == conn.project_id,
                Service.slug == self._generate_slug(name),
            )
        )
        svc = result.scalar_one_or_none()
        created = False

        if not svc:
            svc = Service(
                project_id=conn.project_id,
                name=name,
                slug=self._generate_slug(name),
                service_type=service_type,
                source="discovered",
                service_metadata=metadata or {},
            )
            self.session.add(svc)
            await self.session.flush()
            created = True

        binding_result = await self.session.execute(
            select(ServiceConnectionBinding).where(
                ServiceConnectionBinding.service_id == svc.id,
                ServiceConnectionBinding.connection_id == conn.id,
            )
        )
        if binding_result.scalar_one_or_none() is None:
            binding = ServiceConnectionBinding(
                project_id=conn.project_id,
                service_id=svc.id,
                connection_id=conn.id,
                usage_type="runtime_inspect",
                priority=100,
                notes="Auto-discovered binding",
            )
            self.session.add(binding)

        return svc if created else None

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
        skip = {
            "systemd",
            "dbus",
            "rsyslog",
            "cron",
            "ssh",
            "sshd",
            "networkd",
            "resolved",
            "timesyncd",
            "udev",
            "polkit",
            "snapd",
            "unattended-upgrades",
            "accounts-daemon",
            "udisks2",
            "ModemManager",
            "NetworkManager",
        }
        return name not in skip

    @staticmethod
    def _generate_slug(name: str) -> str:
        slug = name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")
