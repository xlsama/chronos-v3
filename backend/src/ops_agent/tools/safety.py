import re
from enum import Enum


class CommandType(str, Enum):
    READ = "read"           # Read-only, auto-execute
    WRITE = "write"         # Write operation, needs approval (MEDIUM)
    DANGEROUS = "dangerous" # High-risk operation, needs approval + red warning (HIGH)
    BLOCKED = "blocked"     # Absolutely forbidden, reject immediately


# Commands that only read system state (whitelist, auto-execute)
READ_PREFIXES = [
    "ls", "cat", "head", "tail", "less", "more", "grep", "awk", "sed",
    "find", "which", "whereis", "whoami", "hostname", "uname",
    "df", "du", "free", "top", "htop", "vmstat", "iostat", "sar",
    "ps", "pgrep", "lsof", "ss", "netstat", "ip", "ifconfig",
    "ping", "traceroute", "dig", "nslookup", "curl",
    "uptime", "w", "who", "last", "dmesg", "journalctl",
    "systemctl status", "systemctl is-active", "systemctl list-units",
    "docker ps", "docker logs", "docker inspect", "docker stats",
    "docker compose ps", "docker compose logs", "docker compose top",
    "docker compose config", "docker compose images", "docker compose version",
    "kubectl get", "kubectl describe", "kubectl logs", "kubectl top",
    "date", "timedatectl", "env", "printenv", "id", "groups",
    "file", "stat", "wc", "sort", "uniq", "cut", "tr",
    "mount", "lsblk", "blkid", "fdisk -l",
    "nginx -t", "nginx -T",
    "supervisorctl status",
    "pm2 list", "pm2 ls", "pm2 status", "pm2 logs", "pm2 show", "pm2 info",
    "crontab -l",
]

# Dangerous patterns (needs approval + red HIGH warning)
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\b",                # rm -rf
    r"mkfs\.",                     # format disk
    r"dd\s+.*of=/dev/",           # overwrite device
    r"DROP\s+(TABLE|DATABASE)",    # drop database/table
    r"TRUNCATE\b",                # truncate table
    r"kill\s+-9\b",               # force kill process
    r"kubectl\s+delete\b",        # K8s delete resource
    r"\bredis-cli\b.*\b(FLUSHALL|FLUSHDB|SHUTDOWN)\b",  # Redis dangerous ops
]

# Write patterns — whitelist commands used in write mode (needs approval, MEDIUM)
WRITE_PATTERNS = [
    r"\bsed\s+.*-i\b",                                    # sed -i (in-place edit)
    r"\bsed\s+.*--in-place\b",                             # sed --in-place
    r"\bcurl\s+.*-X\s*(POST|PUT|DELETE|PATCH)\b",          # curl with write methods
    r"\bcurl\s+.*(-d\s|--data|--data-raw|--data-binary)",  # curl with request body
    r"\bwget\s",                                            # wget (downloads files)
    r"\btee\s+\S",                                          # tee with file arg (writes)
    r"\b(mysql|mariadb|psql)\b.*\b(INSERT|UPDATE|DELETE|ALTER|CREATE|GRANT|REVOKE)\b",  # SQL write ops
]

# Read-only patterns for service CLIs (regex, case-insensitive)
READ_PATTERNS = [
    # Redis — data reads
    r"\bredis-cli\b.*\b(GET|MGET|HGET|HGETALL|HMGET|HKEYS|HVALS|HLEN|HEXISTS)\b",
    r"\bredis-cli\b.*\b(LRANGE|LLEN|LINDEX)\b",
    r"\bredis-cli\b.*\b(SMEMBERS|SCARD|SISMEMBER|SRANDMEMBER)\b",
    r"\bredis-cli\b.*\b(ZRANGE|ZREVRANGE|ZCARD|ZSCORE|ZRANK|ZCOUNT)\b",
    r"\bredis-cli\b.*\b(KEYS|SCAN|TYPE|TTL|PTTL|EXISTS|DBSIZE|STRLEN|OBJECT|RANDOMKEY)\b",
    # Redis — server info
    r"\bredis-cli\b.*\b(INFO|PING|TIME)\b",
    r"\bredis-cli\b.*\b(CONFIG\s+GET|CLIENT\s+LIST|SLOWLOG\s+(GET|LEN))\b",
    r"\bredis-cli\b.*\b(CLUSTER\s+(INFO|NODES)|MEMORY\s+(USAGE|STATS))\b",
    r"\bredis-cli\s+.*--(scan|bigkeys|stat|latency)\b",
    # MySQL / MariaDB — read-only SQL
    r"\b(mysql|mariadb)\b.*-e\s+[\"']\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b",
    # PostgreSQL — read-only SQL / meta commands
    r"\bpsql\b.*-c\s+[\"']\s*(SELECT|SHOW|EXPLAIN)\b",
    r"\bpsql\b\s+.*(-l|--list)\b",
    # etcdctl reads
    r"\betcdctl\s+(get|endpoint\s+(health|status)|member\s+list|alarm\s+list|version)\b",
    # rabbitmqctl reads
    r"\brabbitmqctl\s+(status|cluster_status|list_queues|list_exchanges|list_bindings|list_connections|list_channels|list_consumers|list_users|list_vhosts|list_permissions)\b",
]

# Absolutely forbidden (never execute, reject immediately)
BLOCKED_PATTERNS = [
    r"rm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\s*$",  # rm -rf /
    r"rm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\*",     # rm -rf /*
    r":\(\)\s*\{",                                          # fork bomb
    r">\s*/dev/sd",                                         # redirect to block device
]


class CommandSafety:
    @staticmethod
    def classify(command: str) -> CommandType:
        cmd = command.strip()

        # 1. BLOCKED → reject immediately
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, cmd):
                return CommandType.BLOCKED

        # 2. DANGEROUS → needs approval + red warning
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return CommandType.DANGEROUS

        # 3. WRITE_PATTERNS → whitelist commands used in write mode
        for pattern in WRITE_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return CommandType.WRITE

        # 4. Split compound commands (||, &&, ;) then pipes
        sub_commands = re.split(r'\|\||&&|;', cmd)
        for sub_cmd in sub_commands:
            parts = [p.strip() for p in sub_cmd.split("|")]
            for part in parts:
                if not part:
                    continue
                is_read = any(part.startswith(prefix) for prefix in READ_PREFIXES)
                if not is_read:
                    is_read = any(re.search(p, part, re.IGNORECASE) for p in READ_PATTERNS)
                if not is_read:
                    return CommandType.WRITE

        # 5. All parts in whitelist → READ
        return CommandType.READ

    @staticmethod
    def compress_output(output: str, max_chars: int = 10000) -> str:
        if len(output) <= max_chars:
            return output
        truncated_count = len(output) - max_chars
        marker = f"\n\n... [truncated {truncated_count} characters] ...\n\n"
        remaining = max_chars - len(marker)
        half = remaining // 2
        return f"{output[:half]}{marker}{output[-half:]}"
