import uuid

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Connection
from src.services.crypto import CryptoService


class ConnectionService:
    def __init__(self, session: AsyncSession, crypto: CryptoService):
        self.session = session
        self.crypto = crypto

    async def create(
        self,
        name: str,
        type: str = "ssh",
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
        project_id: uuid.UUID | None = None,
    ) -> Connection:
        conn_config = None
        if type == "kubernetes" and kubeconfig:
            config_data = {"kubeconfig": kubeconfig}
            if context:
                config_data["context"] = context
            if namespace:
                config_data["namespace"] = namespace
            conn_config = self.crypto.encrypt(orjson.dumps(config_data).decode())

        conn = Connection(
            name=name,
            type=type,
            host=host,
            port=port,
            username=username,
            encrypted_password=self.crypto.encrypt(password) if password else None,
            encrypted_private_key=self.crypto.encrypt(private_key) if private_key else None,
            conn_config=conn_config,
            project_id=project_id,
        )
        self.session.add(conn)
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
