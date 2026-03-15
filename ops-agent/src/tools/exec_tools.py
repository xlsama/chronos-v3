from src.connectors.ssh import SSHConnector
from src.tools.safety import CommandSafety, CommandType

# Registry of SSH connectors by infrastructure ID
_ssh_registry: dict[str, SSHConnector] = {}


def register_ssh_connector(infra_id: str, connector: SSHConnector):
    _ssh_registry[infra_id] = connector


def get_ssh_connector(infra_id: str) -> SSHConnector:
    connector = _ssh_registry.get(infra_id)
    if not connector:
        raise ValueError(f"No SSH connector registered for infrastructure: {infra_id}")
    return connector


async def exec_read(infra_id: str, command: str) -> dict:
    cmd_type = CommandSafety.classify(command)

    if cmd_type == CommandType.BLOCKED:
        return {"error": "Command blocked: this command is too dangerous to execute"}

    if cmd_type == CommandType.WRITE:
        return {"error": "This is a write command. Use exec_write instead, which requires approval."}

    connector = get_ssh_connector(infra_id)
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

    connector = get_ssh_connector(infra_id)
    result = await connector.execute(command)

    return {
        "exit_code": result.exit_code,
        "stdout": CommandSafety.compress_output(result.stdout),
        "stderr": result.stderr,
        "error": None,
    }
