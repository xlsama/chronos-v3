import asyncio
import shlex
import time

from langchain_core.tools import StructuredTool

from src.env import get_settings
from src.lib.logger import get_logger
from src.ops_agent.tools.base_tool import BaseTool, PermissionBehavior, PermissionResult
from src.ops_agent.tools.truncation import truncate_output
from src.ops_agent.tools.safety import CommandType, ShellSafety

log = get_logger(component="bash")

# ── Bash Tool Prompt ──

_BASH_PROMPT = """\
在 Chronos 后端服务器本地执行 Shell 命令。

## 适用场景
- Docker 容器管理：docker ps, docker logs, docker restart
- Kubernetes 操作：kubectl get pods, kubectl describe, kubectl logs
- 系统服务：systemctl status/restart
- API 调用：curl, wget
- 文件查看：cat, tail, less
- 系统信息：df -h, free -m, ps aux

## 不适用（使用其他工具）
- 远程服务器命令 → 用 ssh_bash
- 数据库/缓存/监控查询 → 用 service_exec

## 参数
- command（必填）：要执行的命令
- explanation（写操作时必填）：说明操作原因和预期影响

## 返回格式
{"exit_code": 0, "stdout": "...", "stderr": "...", "error": null}
- exit_code=0 表示成功，非零表示失败
- error 非空表示系统级错误（超时、拦截等）

## 安全规则
- 只读命令自动执行，写操作需人工审批，危险命令被拦截
- 不要在命令中使用 2>/dev/null，系统需要 stderr 中的错误信息

## 最佳实践
- 检查 exit_code 判断命令是否成功，不要只看 stdout
- 用 docker logs --tail 100 限制日志行数，避免输出过大
- 长时间运行的命令可能超时，用 nohup 或 & 放后台
- 多个独立命令用 && 串联：docker ps && kubectl get pods
- 避免交互式命令（vi, top, less 等）
- 写操作必须在 explanation 中说明原因和预期影响
"""

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


async def _execute_local(command: str) -> dict:
    """Execute a command on the local backend server (internal implementation)."""
    # Defense-in-depth: always block dangerous commands
    cmd_type = ShellSafety.classify(command, local=True)
    if cmd_type == CommandType.BLOCKED:
        log.warning("BLOCKED", command=command)
        return {"error": "命令被系统拦截：本地环境禁止执行此命令"}

    log.info("Local executing", cmd_type=cmd_type.name, command_len=len(command))
    log.debug("Local executing", command=command)

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
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": f"命令执行超时（{get_settings().command_timeout}秒）",
        }
    except OSError as e:
        log.error("OS error", error=str(e))
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": f"执行失败: {e}",
        }
    except Exception as e:
        log.error("Unexpected error", error=str(e))
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "error": f"执行异常: {type(e).__name__}: {e}",
        }

    stdout_str = stdout.decode(errors="replace")
    stderr_str = stderr.decode(errors="replace")

    log.info(
        "Result",
        elapsed=f"{exec_elapsed:.2f}s",
        exit_code=proc.returncode,
        stdout_len=len(stdout_str),
        stderr_len=len(stderr_str),
    )
    log.debug("stdout", stdout=stdout_str)
    if stderr_str:
        log.debug("stderr", stderr=stderr_str)

    return {
        "exit_code": proc.returncode,
        "stdout": stdout_str,
        "stderr": stderr_str,
        "error": None,
    }


class BashTool(BaseTool):
    """本地 Shell 命令执行工具。"""

    @property
    def name(self) -> str:
        return "bash"

    @property
    def summary(self) -> str:
        return "在本地执行命令（docker/kubectl/systemctl/curl 等）"

    @property
    def prompt(self) -> str:
        return _BASH_PROMPT

    def is_read_only(self, **kwargs) -> bool:
        return ShellSafety.classify(kwargs.get("command", ""), local=True) == CommandType.READ

    def is_destructive(self, **kwargs) -> bool:
        return ShellSafety.classify(kwargs.get("command", ""), local=True) == CommandType.DANGEROUS

    def is_concurrency_safe(self, **kwargs) -> bool:
        return self.is_read_only(**kwargs)

    async def check_permissions(self, **kwargs) -> PermissionResult:
        cmd_type = ShellSafety.classify(kwargs.get("command", ""), local=True)
        if cmd_type == CommandType.BLOCKED:
            return PermissionResult(PermissionBehavior.DENY, "命令被系统拦截")
        if cmd_type == CommandType.DANGEROUS:
            return PermissionResult(PermissionBehavior.ASK, risk_level="HIGH")
        if cmd_type == CommandType.WRITE:
            return PermissionResult(PermissionBehavior.ASK, risk_level="MEDIUM")
        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute(self, **kwargs) -> dict:
        return await _execute_local(kwargs.get("command", ""))

    def _build_langchain_tool(self):
        tool_self = self

        async def _execute(command: str, explanation: str = "") -> dict:
            result = await tool_self.execute(command=command)
            return truncate_output(result, tool_self.max_result_size_chars)

        return StructuredTool.from_function(
            coroutine=_execute,
            name=self.name,
            description=self.prompt,
        )
