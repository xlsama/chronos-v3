import uuid

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Connection, Project
from src.lib.errors import ValidationError
from src.services.crypto import CryptoService


class ConnectionService:
    def __init__(self, session: AsyncSession, crypto: CryptoService):
        self.session = session
        self.crypto = crypto

    async def create(
        self,
        name: str,
        project_id: uuid.UUID | None = None,
        type: str = "ssh",
        description: str | None = None,
        # SSH fields
        host: str = "",
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        private_key: str | None = None,
        # K8s fields
        kubeconfig: str | None = None,
        context: str | None = None,
        namespace: str | None = None,
        capabilities: list[str] | None = None,
        scope_metadata: dict | None = None,
    ) -> Connection:
        if project_id:
            project = await self.session.get(Project, project_id)
            if not project:
                raise ValidationError("Project not found")

        if type not in {"ssh", "kubernetes"}:
            raise ValidationError(f"Unsupported connection type: {type}")

        if type == "ssh" and not host:
            raise ValidationError("SSH connection requires host")

        if type == "kubernetes" and not kubeconfig:
            raise ValidationError("Kubernetes connection requires kubeconfig")

        dup_filters = [Connection.name == name]
        if project_id:
            dup_filters.append(Connection.project_id == project_id)
        else:
            dup_filters.append(Connection.project_id.is_(None))
        duplicate_stmt = select(Connection).where(*dup_filters)
        duplicate = (await self.session.execute(duplicate_stmt)).scalar_one_or_none()
        if duplicate:
            raise ValidationError("Connection name already exists")

        conn_config = None
        scope_metadata = dict(scope_metadata or {})

        if type == "kubernetes" and kubeconfig:
            config_data = {"kubeconfig": kubeconfig}
            if context:
                config_data["context"] = context
            if namespace:
                config_data["namespace"] = namespace
                scope_metadata.setdefault("namespace", namespace)
            conn_config = self.crypto.encrypt(orjson.dumps(config_data).decode())

        resolved_capabilities = capabilities or self._default_capabilities(type)
        conn = Connection(
            name=name,
            type=type,
            description=description,
            host=host,
            port=port,
            username=username,
            encrypted_password=self.crypto.encrypt(password) if password else None,
            encrypted_private_key=self.crypto.encrypt(private_key) if private_key else None,
            conn_config=conn_config,
            capabilities=resolved_capabilities,
            scope_metadata=scope_metadata,
            project_id=project_id,
        )
        self.session.add(conn)
        await self.session.commit()
        await self.session.refresh(conn)
        return conn

    async def update(self, conn: Connection, **kwargs: object) -> Connection:
        # Name uniqueness check (exclude self)
        if "name" in kwargs:
            dup_filters = [Connection.name == kwargs["name"], Connection.id != conn.id]
            if conn.project_id:
                dup_filters.append(Connection.project_id == conn.project_id)
            else:
                dup_filters.append(Connection.project_id.is_(None))
            dup = (
                await self.session.execute(select(Connection).where(*dup_filters))
            ).scalar_one_or_none()
            if dup:
                raise ValidationError("Connection name already exists")

        # Plain fields
        for field in ("name", "description", "host", "port", "username"):
            if field in kwargs:
                setattr(conn, field, kwargs[field])

        # Re-encrypt sensitive fields
        if "password" in kwargs:
            pw = kwargs["password"]
            conn.encrypted_password = self.crypto.encrypt(pw) if pw else None
        if "private_key" in kwargs:
            pk = kwargs["private_key"]
            conn.encrypted_private_key = self.crypto.encrypt(pk) if pk else None

        # K8s conn_config rebuild
        k8s_fields = {"kubeconfig", "context", "namespace"}
        if k8s_fields & kwargs.keys() and conn.type == "kubernetes":
            # Read current config as base
            current = self.get_decrypted_conn_config(conn) or {}
            kubeconfig = kwargs.get("kubeconfig", current.get("kubeconfig"))
            if not kubeconfig:
                raise ValidationError("Kubernetes connection requires kubeconfig")
            config_data: dict[str, str] = {"kubeconfig": kubeconfig}
            context = kwargs.get("context", current.get("context"))
            if context:
                config_data["context"] = context
            namespace = kwargs.get("namespace", current.get("namespace"))
            if namespace:
                config_data["namespace"] = namespace
                scope_metadata = dict(conn.scope_metadata or {})
                scope_metadata["namespace"] = namespace
                conn.scope_metadata = scope_metadata
            conn.conn_config = self.crypto.encrypt(
                orjson.dumps(config_data).decode()
            )

        await self.session.commit()
        await self.session.refresh(conn)
        return conn

    def get_decrypted_credentials(
        self, conn: Connection
    ) -> tuple[str | None, str | None]:
        password = (
            self.crypto.decrypt(conn.encrypted_password)
            if conn.encrypted_password
            else None
        )
        private_key = (
            self.crypto.decrypt(conn.encrypted_private_key)
            if conn.encrypted_private_key
            else None
        )
        return password, private_key

    def get_decrypted_conn_config(self, conn: Connection) -> dict | None:
        if not conn.conn_config:
            return None
        return orjson.loads(self.crypto.decrypt(conn.conn_config))

    @staticmethod
    def _default_capabilities(conn_type: str) -> list[str]:
        defaults: dict[str, list[str]] = {
            "ssh": ["shell", "logs"],
            "kubernetes": ["k8s_exec", "logs"],
        }
        return defaults.get(conn_type, ["runtime_inspect"])
