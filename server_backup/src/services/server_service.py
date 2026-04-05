from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Server
from src.lib.errors import ValidationError
from src.services.crypto import CryptoService


class ServerService:
    def __init__(self, session: AsyncSession, crypto: CryptoService):
        self.session = session
        self.crypto = crypto

    async def create(
        self,
        name: str,
        description: str | None = None,
        host: str = "",
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        private_key: str | None = None,
        bastion_host: str | None = None,
        bastion_port: int | None = None,
        bastion_username: str | None = None,
        bastion_password: str | None = None,
        bastion_private_key: str | None = None,
        sudo_password: str | None = None,
        use_ssh_password_for_sudo: bool = True,
    ) -> Server:
        if not host:
            raise ValidationError("SSH server requires host")

        duplicate = (
            await self.session.execute(select(Server).where(Server.name == name))
        ).scalar_one_or_none()
        if duplicate:
            raise ValidationError("Server name already exists")

        server = Server(
            name=name,
            description=description,
            host=host,
            port=port,
            username=username,
            encrypted_password=self.crypto.encrypt(password) if password else None,
            encrypted_private_key=self.crypto.encrypt(private_key) if private_key else None,
            bastion_host=bastion_host,
            bastion_port=bastion_port,
            bastion_username=bastion_username,
            encrypted_bastion_password=(
                self.crypto.encrypt(bastion_password) if bastion_password else None
            ),
            encrypted_bastion_private_key=(
                self.crypto.encrypt(bastion_private_key) if bastion_private_key else None
            ),
            encrypted_sudo_password=(self.crypto.encrypt(sudo_password) if sudo_password else None),
            use_ssh_password_for_sudo=use_ssh_password_for_sudo,
        )
        self.session.add(server)
        await self.session.commit()
        await self.session.refresh(server)
        return server

    async def update(self, server: Server, **kwargs: object) -> Server:
        # Name uniqueness check (exclude self)
        if "name" in kwargs:
            dup = (
                await self.session.execute(
                    select(Server).where(Server.name == kwargs["name"], Server.id != server.id)
                )
            ).scalar_one_or_none()
            if dup:
                raise ValidationError("Server name already exists")

        # Plain fields
        for field in (
            "name",
            "description",
            "host",
            "port",
            "username",
            "bastion_host",
            "bastion_port",
            "bastion_username",
            "use_ssh_password_for_sudo",
        ):
            if field in kwargs:
                setattr(server, field, kwargs[field])

        # Re-encrypt sensitive fields
        if "password" in kwargs:
            pw = kwargs["password"]
            server.encrypted_password = self.crypto.encrypt(pw) if pw else None
        if "private_key" in kwargs:
            pk = kwargs["private_key"]
            server.encrypted_private_key = self.crypto.encrypt(pk) if pk else None
        if "bastion_password" in kwargs:
            bp = kwargs["bastion_password"]
            server.encrypted_bastion_password = self.crypto.encrypt(bp) if bp else None
        if "bastion_private_key" in kwargs:
            bk = kwargs["bastion_private_key"]
            server.encrypted_bastion_private_key = self.crypto.encrypt(bk) if bk else None
        if "sudo_password" in kwargs:
            sp = kwargs["sudo_password"]
            server.encrypted_sudo_password = self.crypto.encrypt(sp) if sp else None

        await self.session.commit()
        await self.session.refresh(server)

        # Invalidate SSH connector cache so new credentials take effect
        from src.ops_agent.tools.ssh_bash_tool import invalidate_connector

        await invalidate_connector(str(server.id))

        return server

    def get_decrypted_credentials(self, server: Server) -> tuple[str | None, str | None]:
        password = (
            self.crypto.decrypt(server.encrypted_password) if server.encrypted_password else None
        )
        private_key = (
            self.crypto.decrypt(server.encrypted_private_key)
            if server.encrypted_private_key
            else None
        )
        return password, private_key

    def get_decrypted_bastion_credentials(self, server: Server) -> tuple[str | None, str | None]:
        password = (
            self.crypto.decrypt(server.encrypted_bastion_password)
            if server.encrypted_bastion_password
            else None
        )
        private_key = (
            self.crypto.decrypt(server.encrypted_bastion_private_key)
            if server.encrypted_bastion_private_key
            else None
        )
        return password, private_key

    def get_sudo_password(self, server: Server) -> str | None:
        """Get sudo password: dedicated sudo_password > SSH password (if enabled) > None."""
        if server.encrypted_sudo_password:
            return self.crypto.decrypt(server.encrypted_sudo_password)
        if server.use_ssh_password_for_sudo and server.encrypted_password:
            return self.crypto.decrypt(server.encrypted_password)
        return None
