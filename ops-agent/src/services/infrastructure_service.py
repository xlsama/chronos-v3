import uuid

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Infrastructure
from src.services.crypto import CryptoService


class InfrastructureService:
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
    ) -> Infrastructure:
        conn_config = None
        if type == "kubernetes" and kubeconfig:
            config_data = {"kubeconfig": kubeconfig}
            if context:
                config_data["context"] = context
            if namespace:
                config_data["namespace"] = namespace
            conn_config = self.crypto.encrypt(orjson.dumps(config_data).decode())

        infra = Infrastructure(
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
        self.session.add(infra)
        await self.session.commit()
        await self.session.refresh(infra)
        return infra

    def get_decrypted_credentials(
        self, infra: Infrastructure
    ) -> tuple[str | None, str | None]:
        password = (
            self.crypto.decrypt(infra.encrypted_password)
            if infra.encrypted_password
            else None
        )
        private_key = (
            self.crypto.decrypt(infra.encrypted_private_key)
            if infra.encrypted_private_key
            else None
        )
        return password, private_key

    def get_decrypted_conn_config(self, infra: Infrastructure) -> dict | None:
        if not infra.conn_config:
            return None
        return orjson.loads(self.crypto.decrypt(infra.conn_config))
