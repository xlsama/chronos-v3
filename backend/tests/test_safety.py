import pytest

from src.ops_agent.tools.safety import (
    CommandSafety,
    CommandType,
    _split_compounds,
    _split_pipes,
)


class TestSplitPipes:
    def test_simple_pipe(self):
        assert _split_pipes("ls | grep foo") == ["ls", "grep foo"]

    def test_pipe_inside_double_quotes(self):
        assert _split_pipes('grep -r "region\\|营收\\|revenue" /app/src') == [
            'grep -r "region\\|营收\\|revenue" /app/src'
        ]

    def test_pipe_inside_single_quotes(self):
        assert _split_pipes("grep -r 'a|b|c' /app") == ["grep -r 'a|b|c' /app"]

    def test_mixed_quoted_and_real_pipe(self):
        assert _split_pipes('grep "a|b" file | wc -l') == [
            'grep "a|b" file',
            "wc -l",
        ]

    def test_multiple_pipes(self):
        assert _split_pipes("cat file | grep foo | wc -l") == [
            "cat file",
            "grep foo",
            "wc -l",
        ]


class TestSplitCompounds:
    def test_and_operator(self):
        assert _split_compounds("ls && cat file") == ["ls", "cat file"]

    def test_or_operator(self):
        assert _split_compounds("ls || echo fail") == ["ls", "echo fail"]

    def test_semicolon(self):
        assert _split_compounds("ls; cat file") == ["ls", "cat file"]

    def test_quoted_operators(self):
        assert _split_compounds('echo "a && b || c; d"') == [
            'echo "a && b || c; d"'
        ]


class TestClassifyBugFixes:
    """Tests for the two specific bugs fixed."""

    def test_grep_with_regex_alternation_is_read(self):
        """Bug 1: pipe inside grep regex should not cause mis-split."""
        cmd = 'grep -r "region\\|营收\\|revenue" /app/src --include="*.ts"'
        assert CommandSafety.classify(cmd) == CommandType.READ

    def test_find_xargs_cat_is_read(self):
        """Bug 2: xargs cat should be READ."""
        cmd = 'find /app/src -type f -name "*.ts" | xargs cat'
        assert CommandSafety.classify(cmd) == CommandType.READ

    def test_xargs_rm_rf_is_dangerous(self):
        """xargs with dangerous sub-command should still be DANGEROUS."""
        cmd = "xargs rm -rf /tmp"
        assert CommandSafety.classify(cmd) == CommandType.DANGEROUS

    def test_xargs_grep_is_read(self):
        cmd = "find . -name '*.py' | xargs grep TODO"
        assert CommandSafety.classify(cmd) == CommandType.READ


class TestClassifyRead:
    def test_simple_ls(self):
        assert CommandSafety.classify("ls -la") == CommandType.READ

    def test_cat_file(self):
        assert CommandSafety.classify("cat /etc/hosts") == CommandType.READ

    def test_grep_pipe(self):
        assert CommandSafety.classify("ps aux | grep nginx") == CommandType.READ

    def test_docker_ps(self):
        assert CommandSafety.classify("docker ps -a") == CommandType.READ

    def test_kubectl_get(self):
        assert CommandSafety.classify("kubectl get pods -n default") == CommandType.READ

    def test_compound_read(self):
        assert CommandSafety.classify("ls && cat /etc/hosts") == CommandType.READ


class TestClassifyWrite:
    def test_unknown_command(self):
        assert CommandSafety.classify("apt install nginx") == CommandType.WRITE

    def test_sed_in_place(self):
        assert CommandSafety.classify("sed -i 's/old/new/' file.txt") == CommandType.WRITE

    def test_curl_post(self):
        assert CommandSafety.classify("curl -X POST http://localhost/api") == CommandType.WRITE


class TestClassifyDangerous:
    def test_rm_rf(self):
        assert CommandSafety.classify("rm -rf /tmp/data") == CommandType.DANGEROUS

    def test_kill_9(self):
        assert CommandSafety.classify("kill -9 1234") == CommandType.DANGEROUS

    def test_docker_rm(self):
        assert CommandSafety.classify("docker rm container1") == CommandType.DANGEROUS

    def test_systemctl_restart(self):
        assert CommandSafety.classify("systemctl restart nginx") == CommandType.DANGEROUS


class TestClassifyBlocked:
    def test_rm_rf_root(self):
        assert CommandSafety.classify("rm -rf /") == CommandType.BLOCKED

    def test_rm_rf_root_star(self):
        assert CommandSafety.classify("rm -rf /*") == CommandType.BLOCKED

    def test_fork_bomb(self):
        assert CommandSafety.classify(":() { :|:& };:") == CommandType.BLOCKED
