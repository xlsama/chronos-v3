import pytest

from src.tools.safety import CommandSafety, CommandType


def test_read_command_allowed():
    result = CommandSafety.classify("df -h")
    assert result == CommandType.READ


def test_common_read_commands():
    for cmd in ["ls -la", "cat /var/log/syslog", "free -m", "top -bn1", "ps aux", "uptime"]:
        assert CommandSafety.classify(cmd) == CommandType.READ, f"{cmd} should be READ"


def test_write_command_detected():
    result = CommandSafety.classify("rm -rf /tmp/old")
    assert result == CommandType.WRITE


def test_common_write_commands():
    for cmd in ["systemctl restart nginx", "apt-get install vim", "kill -9 1234", "mkdir /tmp/x"]:
        assert CommandSafety.classify(cmd) == CommandType.WRITE, f"{cmd} should be WRITE"


def test_dangerous_commands_blocked():
    for cmd in [
        "rm -rf /",
        "rm -rf /*",
        "mkfs.ext4 /dev/sda",
        "dd if=/dev/zero of=/dev/sda",
        "> /dev/sda",
        "chmod -R 777 /",
        ":(){ :|:& };:",
    ]:
        assert CommandSafety.classify(cmd) == CommandType.BLOCKED, f"{cmd} should be BLOCKED"


def test_pipe_command_classification():
    assert CommandSafety.classify("ps aux | grep nginx") == CommandType.READ
    assert CommandSafety.classify("echo test | tee /tmp/file") == CommandType.WRITE


def test_compress_output():
    long_output = "x" * 20000
    compressed = CommandSafety.compress_output(long_output, max_chars=10000)
    assert len(compressed) <= 10000
    assert "... [truncated" in compressed


def test_compress_output_short():
    short = "hello"
    assert CommandSafety.compress_output(short) == short
