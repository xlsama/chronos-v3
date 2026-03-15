import uuid

from src.connectors.ssh import SSHConnector
from src.tools.safety import CommandSafety, CommandType

# Registry of SSH connectors by infrastructure ID
_ssh_registry: dict[str, SSHConnector] = {}


def register_ssh_connector(infra_id: str, connector: SSHConnector):
    _ssh_registry[infra_id] = connector


async def get_ssh_connector(infra_id: str) -> SSHConnector:
    # 1. Check registry cache
    if infra_id in _ssh_registry:
        return _ssh_registry[infra_id]

    # 2. Cache miss → query DB → decrypt credentials → create SSHConnector → cache
    from src.db.connection import get_session_factory
    from src.db.models import Infrastructure
    from src.services.crypto import CryptoService
    from src.config import get_settings

    factory = get_session_factory()
    async with factory() as session:
        infra = await session.get(Infrastructure, uuid.UUID(infra_id))
        if not infra:
            raise ValueError(f"Infrastructure not found: {infra_id}")

        crypto = CryptoService(key=get_settings().encryption_key)
        password = crypto.decrypt(infra.encrypted_password) if infra.encrypted_password else None
        private_key = (
            crypto.decrypt(infra.encrypted_private_key) if infra.encrypted_private_key else None
        )

        connector = SSHConnector(
            host=infra.host,
            port=infra.port,
            username=infra.username,
            password=password,
            private_key=private_key,
        )
        _ssh_registry[infra_id] = connector
        return connector


async def exec_read(infra_id: str, command: str) -> dict:
    cmd_type = CommandSafety.classify(command)

    if cmd_type == CommandType.BLOCKED:
        return {"error": "Command blocked: this command is too dangerous to execute"}

    if cmd_type == CommandType.WRITE:
        return {"error": "This is a write command. Use exec_write instead, which requires approval."}

    connector = await get_ssh_connector(infra_id)
    result = await connector.execute(command)

    return {
        "exit_code": result.exit_code,
        "stdout": CommandSafety.compress_output(result.stdout),
        "stderr": result.stderr,
        "error": None,
    }


async def exec_write(infra_id: str, command: str) -> dict:
    cmd_type = CommandSafety.classify(command)

    if cmd_type == CommandType.BLOCKED:
        return {"error": "Command blocked: this command is too dangerous to execute"}

    connector = await get_ssh_connector(infra_id)
    result = await connector.execute(command)

    return {
        "exit_code": result.exit_code,
        "stdout": CommandSafety.compress_output(result.stdout),
        "stderr": result.stderr,
        "error": None,
    }
