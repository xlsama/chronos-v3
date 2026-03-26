from types import SimpleNamespace

from src.ops_agent.nodes.main_agent import _build_runtime_hints
from src.ops_agent.tools.tool_classifier import CommandType, ServiceSafety, ShellSafety


def test_shell_safety_treats_timeout_wrapped_tcp_probe_as_read():
    command = (
        "timeout 5 bash -c 'echo > /dev/tcp/10.200.100.85/8082' 2>&1 "
        '&& echo "Port 8082 is open" || echo "Port 8082 connection failed"'
    )

    assert ShellSafety.classify(command, local=True) is CommandType.READ


def test_shell_safety_treats_pwd_and_readlink_as_read():
    command = "pwd; echo '---'; readlink /proc/20450/cwd"

    assert ShellSafety.classify(command) is CommandType.READ


def test_service_safety_treats_mongodb_ping_as_read():
    assert ServiceSafety.classify("mongodb", '{"ping": 1}') is CommandType.READ


def test_runtime_hints_are_disabled_even_when_state_has_signals():
    state = {
        "messages": [
            SimpleNamespace(
                tool_calls=[{"id": "call_list_servers", "name": "list_servers"}],
                content="",
            ),
            SimpleNamespace(
                tool_call_id="call_list_servers",
                content="当前没有注册任何服务器（servers 表为空）。无法使用 ssh_bash 工具。",
            ),
            SimpleNamespace(
                tool_calls=[{"id": "call_service_exec", "name": "service_exec"}],
                content="",
            ),
            SimpleNamespace(
                tool_call_id="call_service_exec",
                content="(integer) True",
            ),
            SimpleNamespace(
                tool_calls=[{"id": "call_bash", "name": "bash"}],
                content="",
            ),
            SimpleNamespace(
                tool_call_id="call_bash",
                content=(
                    '{"exit_code": 0, "stdout": "* Connected to 10.200.100.85 '
                    '(10.200.100.85) port 8082\\n* Request completely sent off\\n", '
                    '"stderr": "", "error": null}'
                ),
            ),
        ],
        "ask_human_count": 1,
    }

    assert _build_runtime_hints(state) == ""


def test_runtime_hints_are_disabled_on_initial_turn():
    state = {
        "messages": [],
        "ask_human_count": 0,
        "kb_summary": None,
        "description": "用户反馈页面接口一直 pending，无响应",
    }

    assert _build_runtime_hints(state) == ""
