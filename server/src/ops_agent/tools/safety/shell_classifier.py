"""Shell 命令安全分类器 —— 对 SSH 和本地 bash 命令进行风险分级。"""

import regex
from enum import Enum


class CommandType(str, Enum):
    READ = "read"  # Read-only, auto-execute
    WRITE = "write"  # Write operation, needs approval (MEDIUM)
    DANGEROUS = "dangerous"  # High-risk operation, needs approval + red warning (HIGH)
    BLOCKED = "blocked"  # Absolutely forbidden, reject immediately


# ═══════════════════════════════════════════
# Internal helpers: quote-aware command splitting
# ═══════════════════════════════════════════


def _split_outside_quotes(cmd: str, delimiters: list[str]) -> list[str]:
    """Split *cmd* on any of *delimiters*, but only outside single/double quotes.

    Longer delimiters are matched first so that ``||`` is preferred over ``|``.
    """
    delimiters = sorted(delimiters, key=len, reverse=True)
    parts: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if ch == "\\" and i + 1 < len(cmd):
            current.append(ch)
            current.append(cmd[i + 1])
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if not in_single and not in_double:
            matched = False
            for delim in delimiters:
                if cmd[i : i + len(delim)] == delim:
                    parts.append("".join(current).strip())
                    current = []
                    i += len(delim)
                    matched = True
                    break
            if matched:
                continue
        current.append(ch)
        i += 1
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def _split_compounds(cmd: str) -> list[str]:
    """Split on ``||``, ``&&``, ``;``, newline outside quotes."""
    return _split_outside_quotes(cmd, ["||", "&&", ";", "\n"])


def _split_pipes(cmd: str) -> list[str]:
    """Split on pipe ``|`` outside quotes (not ``||``)."""
    return _split_outside_quotes(cmd, ["|"])


def _strip_timeout_wrapper(cmd: str) -> str:
    """Strip a leading `timeout <duration>` wrapper for read/write classification."""
    text = cmd.strip()
    while text.startswith("timeout "):
        parts = text.split(None, 2)
        if len(parts) < 3:
            return text
        text = parts[2].strip()
    return text


_SUDO_FLAGS_WITH_ARG = frozenset("ugpCrtD")


def _strip_sudo_prefix(cmd: str) -> tuple[str, bool]:
    """Strip 'sudo [-flags]' prefix for classification. Returns (inner_cmd, had_sudo)."""
    tokens = cmd.split()
    if not tokens or tokens[0] != "sudo":
        return cmd, False
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        flag = tokens[i]
        i += 1
        # Flags like -u, -g, -p take a separate argument
        if len(flag) == 2 and flag[1] in _SUDO_FLAGS_WITH_ARG and i < len(tokens):
            i += 1
    if i >= len(tokens):
        return "", True
    return " ".join(tokens[i:]), True


def _unquoted_text(cmd: str) -> str:
    """Return *cmd* with quoted content replaced by spaces, for metacharacter scanning."""
    out: list[str] = []
    in_sq = in_dq = False
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if ch == "\\" and i + 1 < len(cmd) and not in_sq:
            out.append("  ")
            i += 2
            continue
        if ch == "'" and not in_dq:
            in_sq = not in_sq
            i += 1
            continue
        if ch == '"' and not in_sq:
            in_dq = not in_dq
            i += 1
            continue
        out.append(ch if (not in_sq and not in_dq) else " ")
        i += 1
    return "".join(out)


# ═══════════════════════════════════════════
# Regex patterns
# ═══════════════════════════════════════════

# Absolutely forbidden (never execute) — pre-compiled, single alternation
_BLOCKED_RE = regex.compile(
    r"|".join(
        [
            r"rm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\s*$",  # rm -rf /
            r"rm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\*",  # rm -rf /*
            r"rm\s+.*--no-preserve-root",  # rm --no-preserve-root
            r":\(\)\s*\{",  # fork bomb
            r">\s*/dev/sd",  # redirect to block device
        ]
    )
)

# Local-only blocked patterns (local=True)
_LOCAL_BLOCKED_RE = regex.compile(
    r"|".join(
        [
            r"\.env\b",
            r"/etc/(shadow|passwd|sudoers)",
        ]
    )
)

# Dangerous patterns (needs approval + red warning) — pre-compiled, IGNORECASE
_DANGEROUS_RE = regex.compile(
    r"|".join(
        [
            r"(^|[;&|]\s*)su\b",
            r"rm\s+-rf\b",
            r"mkfs\.",
            r"dd\s+.*of=/dev/",
            r"DROP\s+(TABLE|DATABASE)",
            r"TRUNCATE\b",
            r"kill\s+-9\b",
            r"kubectl\s+delete\b",
            r"\bredis-cli\b.*\b(FLUSHALL|FLUSHDB|SHUTDOWN)\b",
            r"\bdocker\s+rm\s+",
            r"\bdocker\s+rmi\s",
            r"\bdocker\s+system\s+prune\b",
            r"\biptables\b",
            r"\bcrontab\s+-[er]\b",
            r"\bsystemctl\s+(stop|restart|disable|enable)\b",
            r"\bdocker\s+compose\s+(down|rm)\b",
            r"\bkubectl\s+(apply|patch|scale|rollout)\b",
        ]
    ),
    regex.IGNORECASE,
)

# Write patterns (needs approval, MEDIUM) — pre-compiled, IGNORECASE
_WRITE_RE = regex.compile(
    r"|".join(
        [
            r"\bsed\s+.*-i\b",
            r"\bsed\s+.*--in-place\b",
            r"\bcurl\s+.*-X\s*(POST|PUT|DELETE|PATCH)\b",
            r"\bcurl\s+.*--request\s*(POST|PUT|DELETE|PATCH)\b",
            r"\bcurl\s+.*(-d\s|--data|--data-raw|--data-binary)",
            r"\bcurl\s+.*(-F\s|--form[\s=]|-T\s|--upload-file[\s=])",
            r"\bwget\s",
            r"\btee\s+\S",
            r"\b(mysql|mariadb|psql)\b.*\b(INSERT|UPDATE|DELETE|ALTER|CREATE|GRANT|REVOKE)\b",
        ]
    ),
    regex.IGNORECASE,
)

# Shell metacharacter patterns
_CMD_SUBSTITUTION_RE = regex.compile(r"\$\(|`")
_REDIRECT_WRITE_RE = regex.compile(r"\d*>{1,2}\s*(?!/dev/null\b)(?!&)\S")
_HEREDOC_RE = regex.compile(r'<<-?\s*\\?[\'"]?\w+')

# Read-only patterns for service CLIs — pre-compiled, IGNORECASE
_READ_RE = regex.compile(
    r"|".join(
        [
            r"\bredis-cli\b.*\b("
            r"GET|MGET|HGET|HGETALL|HMGET|HKEYS|HVALS|HLEN|HEXISTS"
            r"|LRANGE|LLEN|LINDEX"
            r"|SMEMBERS|SCARD|SISMEMBER|SRANDMEMBER"
            r"|ZRANGE|ZREVRANGE|ZCARD|ZSCORE|ZRANK|ZCOUNT"
            r"|KEYS|SCAN|TYPE|TTL|PTTL|EXISTS|DBSIZE|STRLEN|OBJECT|RANDOMKEY"
            r"|INFO|PING|TIME"
            r")\b",
            r"\bredis-cli\b.*\b(CONFIG\s+GET|CLIENT\s+LIST|SLOWLOG\s+(GET|LEN))\b",
            r"\bredis-cli\b.*\b(CLUSTER\s+(INFO|NODES)|MEMORY\s+(USAGE|STATS))\b",
            r"\bredis-cli\s+.*--(scan|bigkeys|stat|latency)\b",
            r"\b(mysql|mariadb)\b.*-e\s+[\"']\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b",
            r"\bpsql\b.*-c\s+[\"']\s*(SELECT|SHOW|EXPLAIN)\b",
            r"\bpsql\b\s+.*(-l|--list)\b",
            r"^java\s+-version\b",
            r"^node\s+(-v|--version)\b",
            r"^npm\s+(-v|--version)\b",
            r"^yarn\s+(-v|--version)\b",
            r"\betcdctl\s+(get|endpoint\s+(health|status)|member\s+list|alarm\s+list|version)\b",
            r"\brabbitmqctl\s+(status|cluster_status|list_queues|list_exchanges|list_bindings"
            r"|list_connections|list_channels|list_consumers|list_users|list_vhosts"
            r"|list_permissions)\b",
        ]
    ),
    regex.IGNORECASE,
)

# SSH read-only command prefixes (whitelist)
_READ_PREFIXES = [
    "ls",
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "grep",
    "awk",
    "sed",
    "echo",
    "nproc",
    "command",
    "sleep",
    "find",
    "which",
    "whereis",
    "whoami",
    "hostname",
    "uname",
    "pwd",
    "readlink",
    "df",
    "du",
    "free",
    "top",
    "htop",
    "vmstat",
    "iostat",
    "sar",
    "ps",
    "pgrep",
    "lsof",
    "ss",
    "netstat",
    "ip",
    "ifconfig",
    "ping",
    "traceroute",
    "dig",
    "nslookup",
    "curl",
    "uptime",
    "w",
    "who",
    "last",
    "dmesg",
    "journalctl",
    "systemctl status",
    "systemctl is-active",
    "systemctl list-units",
    "docker ps",
    "docker logs",
    "docker inspect",
    "docker stats",
    "docker version",
    "docker info",
    "docker top",
    "docker port",
    "docker network ls",
    "docker network inspect",
    "docker volume ls",
    "docker images",
    "docker system df",
    "docker compose ps",
    "docker compose logs",
    "docker compose top",
    "docker compose config",
    "docker compose images",
    "docker compose version",
    "kubectl get",
    "kubectl describe",
    "kubectl logs",
    "kubectl top",
    "date",
    "timedatectl",
    "env",
    "printenv",
    "id",
    "groups",
    "file",
    "stat",
    "wc",
    "sort",
    "uniq",
    "cut",
    "tr",
    "mount",
    "lsblk",
    "blkid",
    "fdisk -l",
    "nginx -t",
    "nginx -T",
    "supervisorctl status",
    "pm2 list",
    "pm2 ls",
    "pm2 status",
    "pm2 logs",
    "pm2 show",
    "pm2 info",
    "crontab -l",
]

# Local read-only command prefixes (aligned with SSH _READ_PREFIXES)
_LOCAL_READ_PREFIXES = _READ_PREFIXES + ["jq"]


# ═══════════════════════════════════════════
# ShellSafety
# ═══════════════════════════════════════════


class ShellSafety:
    @staticmethod
    def classify(command: str, local: bool = False) -> CommandType:
        """Classify a shell command. local=True enables stricter local execution policy.

        sudo/su prefixes are stripped before classification — approval is based on
        the actual operation, not the privilege escalation mechanism.
        """
        cmd = command.strip()

        # 1. BLOCKED: universal dangerous patterns (checked on raw command)
        if _BLOCKED_RE.search(cmd):
            return CommandType.BLOCKED

        # 2. BLOCKED: local-only patterns (sensitive file access)
        if local and _LOCAL_BLOCKED_RE.search(cmd):
            return CommandType.BLOCKED

        # 3. Per-sub-command classification with sudo stripping
        read_prefixes = _LOCAL_READ_PREFIXES if local else _READ_PREFIXES
        worst = CommandType.READ

        sub_commands = _split_compounds(cmd)
        for sub_cmd in sub_commands:
            parts = _split_pipes(sub_cmd)
            for part in parts:
                if not part:
                    continue
                normalized = _strip_timeout_wrapper(part)
                inner, _ = _strip_sudo_prefix(normalized)

                # DANGEROUS: return immediately (highest actionable severity)
                if _DANGEROUS_RE.search(inner):
                    return CommandType.DANGEROUS

                # WRITE patterns
                if _WRITE_RE.search(inner):
                    worst = CommandType.WRITE
                    continue

                # Shell metacharacter escalation (checked outside quotes only)
                unquoted = _unquoted_text(inner)
                if _CMD_SUBSTITUTION_RE.search(unquoted):
                    worst = CommandType.WRITE
                    continue
                if _REDIRECT_WRITE_RE.search(unquoted):
                    worst = CommandType.WRITE
                    continue
                if _HEREDOC_RE.search(unquoted):
                    worst = CommandType.WRITE
                    continue

                # READ whitelist (prefix match + regex patterns)
                is_read = any(inner.startswith(prefix) for prefix in read_prefixes)
                if not is_read:
                    is_read = bool(_READ_RE.search(inner))
                if not is_read:
                    worst = CommandType.WRITE

        return worst
