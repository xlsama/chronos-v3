import uuid

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
        host: str,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        private_key: str | None = None,
        project_id: uuid.UUID | None = None,
    ) -> Infrastructure:
        infra = Infrastructure(
            name=name,
            host=host,
            port=port,
            username=username,
            encrypted_password=self.crypto.encrypt(password) if password else None,
            encrypted_private_key=self.crypto.encrypt(private_key) if private_key else None,
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
