import re
from enum import Enum


class CommandType(str, Enum):
    READ = "read"
    WRITE = "write"
    BLOCKED = "blocked"


# Commands that only read system state
READ_PREFIXES = [
    "ls", "cat", "head", "tail", "less", "more", "grep", "awk", "sed",
    "find", "which", "whereis", "whoami", "hostname", "uname",
    "df", "du", "free", "top", "htop", "vmstat", "iostat", "sar",
    "ps", "pgrep", "lsof", "ss", "netstat", "ip", "ifconfig", "ping", "traceroute",
    "dig", "nslookup", "curl", "wget",
    "uptime", "w", "who", "last", "dmesg", "journalctl",
    "systemctl status", "systemctl is-active", "systemctl list-units",
    "docker ps", "docker logs", "docker inspect", "docker stats",
    "kubectl get", "kubectl describe", "kubectl logs", "kubectl top",
    "date", "timedatectl", "env", "printenv", "id", "groups",
    "file", "stat", "wc", "sort", "uniq", "cut", "tr", "tee",
    "mount", "lsblk", "blkid", "fdisk -l",
]

# Patterns that are always blocked (catastrophic)
BLOCKED_PATTERNS = [
    r"rm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\s*$",   # rm -rf /
    r"rm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\*",      # rm -rf /*
    r"mkfs\.",                                                # format disk
    r"dd\s+.*of=/dev/",                                      # overwrite device
    r">\s*/dev/sd",                                           # redirect to device
    r"chmod\s+(-[a-zA-Z]*)?\s*777\s+/\s*$",                 # chmod 777 /
    r":\(\)\s*\{",                                           # fork bomb
]


class CommandSafety:
    @staticmethod
    def classify(command: str) -> CommandType:
        cmd = command.strip()

        # Check blocked patterns first
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, cmd):
                return CommandType.BLOCKED

        # For piped commands, classify by the most "dangerous" part
        parts = [p.strip() for p in cmd.split("|")]
        has_write = False
        for part in parts:
            first_word = part.split()[0] if part.split() else ""
            # Check if it matches a read prefix
            is_read = any(
                part.startswith(prefix) for prefix in READ_PREFIXES
            )
            if not is_read:
                has_write = True

        return CommandType.READ if not has_write else CommandType.WRITE

    @staticmethod
    def compress_output(output: str, max_chars: int = 10000) -> str:
        if len(output) <= max_chars:
            return output
        truncated_count = len(output) - max_chars
        marker = f"\n\n... [truncated {truncated_count} characters] ...\n\n"
        remaining = max_chars - len(marker)
        half = remaining // 2
        return f"{output[:half]}{marker}{output[-half:]}"
