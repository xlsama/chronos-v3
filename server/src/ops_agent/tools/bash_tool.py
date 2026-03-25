import asyncio
import shlex
import time

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.tools.tool_permissions import ShellSafety, CommandType, compress_output

log = get_logger(component="bash")

# Default work directory for local bash execution
_WORK_DIR = "/tmp"


def _wrap_local_command(command: str) -> str:
    wrapped = f"set -o pipefail; {command}"
    quoted = shlex.quote(wrapped)
    return (
        "if command -v bash >/dev/null 2>&1; "
        f"then bash -lc {quoted}; "
        f"else sh -c {shlex.quote(command)}; fi"
    )


async def local_bash(command: str) -> dict:
    """Execute a command on the local backend server."""
    cmd_type = ShellSafety.classify(command, local=True)

    log.info("Local executing", cmd_type=cmd_type.name, command_len=len(command))
    log.debug("Local executing", command=command)

    if cmd_type == CommandType.BLOCKED:
        log.warning("BLOCKED", command=command)
        return {"error": "命令被系统拦截：本地环境禁止执行此命令"}

    try:
        wrapped_command = _wrap_local_command(command)
        proc = await asyncio.create_subprocess_shell(
            wrapped_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_WORK_DIR,
        )
        t0 = time.monotonic()
        settings = get_settings()
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=settings.command_timeout
        )
        exec_elapsed = time.monotonic() - t0
    except asyncio.TimeoutError:
        log.warning("Timeout", limit=f"{get_settings().command_timeout}s")
        return {"error": f"命令执行超时（{get_settings().command_timeout}秒）"}
    except OSError as e:
        log.error("OS error", error=str(e))
        return {"error": f"执行失败: {e}"}
    except Exception as e:
        log.error("Unexpected error", error=str(e))
        return {"error": f"执行异常: {e}"}

    stdout_str = compress_output(stdout.decode(errors="replace"))
    stderr_str = stderr.decode(errors="replace")

    log.info("Result", elapsed=f"{exec_elapsed:.2f}s", exit_code=proc.returncode, stdout_len=len(stdout_str), stderr_len=len(stderr_str))
    log.debug("stdout", stdout=stdout_str)
    if stderr_str:
        log.debug("stderr", stderr=stderr_str)

    return {
        "exit_code": proc.returncode,
        "stdout": stdout_str,
        "stderr": stderr_str,
        "error": None,
    }
