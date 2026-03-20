import asyncio
import time

from src.lib.logger import logger
from src.ops_agent.tools.tool_permissions import ShellSafety, CommandType, compress_output

# Default work directory for local bash execution
_WORK_DIR = "/tmp"


async def local_bash(command: str) -> dict:
    """Execute a command on the local backend server."""
    cmd_type = ShellSafety.classify(command, local=True)

    logger.info(f"\n[bash] Local executing: cmd_type={cmd_type.name}, command={command[:100]}")

    if cmd_type == CommandType.BLOCKED:
        logger.warning(f"[bash] BLOCKED: {command[:100]}")
        return {"error": "命令被系统拦截：本地环境禁止执行此命令"}

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_WORK_DIR,
        )
        t0 = time.monotonic()
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        exec_elapsed = time.monotonic() - t0
    except asyncio.TimeoutError:
        logger.warning("[bash] Timeout after 30s")
        return {"error": "命令执行超时（30秒）"}
    except OSError as e:
        logger.error(f"[bash] OS error: {e}")
        return {"error": f"执行失败: {e}"}
    except Exception as e:
        logger.error(f"[bash] Unexpected error: {e}")
        return {"error": f"执行异常: {e}"}

    stdout_str = compress_output(stdout.decode(errors="replace"))
    stderr_str = stderr.decode(errors="replace")

    logger.info(f"[bash] Result in {exec_elapsed:.2f}s: exit_code={proc.returncode}, stdout_len={len(stdout_str)}, stderr_len={len(stderr_str)}")
    logger.debug(f"[bash] stdout: {stdout_str[:500]}")
    if stderr_str:
        logger.debug(f"[bash] stderr: {stderr_str[:500]}")

    return {
        "exit_code": proc.returncode,
        "stdout": stdout_str,
        "stderr": stderr_str,
        "error": None,
    }
