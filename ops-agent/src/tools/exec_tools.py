import uuid

import orjson

from src.connectors.k8s import K8sConnector
from src.connectors.ssh import SSHConnector
from src.tools.safety import CommandSafety, CommandType

# Registry of connectors by infrastructure ID
_connector_registry: dict[str, SSHConnector | K8sConnector] = {}


def register_connector(infra_id: str, connector: SSHConnector | K8sConnector):
    _connector_registry[infra_id] = connector


async def get_connector(infra_id: str) -> SSHConnector | K8sConnector:
    # 1. Check registry cache
    if infra_id in _connector_registry:
        return _connector_registry[infra_id]

    # 2. Cache miss → query DB → create connector by type → cache
    from src.config import get_settings
    from src.db.connection import get_session_factory
    from src.db.models import Infrastructure
    from src.services.crypto import CryptoService

    factory = get_session_factory()
    async with factory() as session:
        infra = await session.get(Infrastructure, uuid.UUID(infra_id))
        if not infra:
            raise ValueError(f"Infrastructure not found: {infra_id}")

        crypto = CryptoService(key=get_settings().encryption_key)

        if infra.type == "kubernetes":
            if not infra.conn_config:
                raise ValueError(f"K8s infrastructure missing conn_config: {infra_id}")
            config = orjson.loads(crypto.decrypt(infra.conn_config))
            connector = K8sConnector(
                kubeconfig=config["kubeconfig"],
                context=config.get("context"),
                namespace=config.get("namespace", "default"),
            )
        else:  # ssh (default)
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

        _connector_registry[infra_id] = connector
        return connector


async def exec_read(infra_id: str, command: str) -> dict:
    cmd_type = CommandSafety.classify(command)

    if cmd_type == CommandType.BLOCKED:
        return {"error": "Command blocked: this command is too dangerous to execute"}

    if cmd_type == CommandType.WRITE:
        return {"error": "This is a write command. Use exec_write instead, which requires approval."}

    connector = await get_connector(infra_id)
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

    connector = await get_connector(infra_id)
    result = await connector.execute(command)

    return {
        "exit_code": result.exit_code,
        "stdout": CommandSafety.compress_output(result.stdout),
        "stderr": result.stderr,
        "error": None,
    }
