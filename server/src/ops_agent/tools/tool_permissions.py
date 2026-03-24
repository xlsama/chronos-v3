import re
from enum import Enum


class CommandType(str, Enum):
    READ = "read"           # Read-only, auto-execute
    WRITE = "write"         # Write operation, needs approval (MEDIUM)
    DANGEROUS = "dangerous" # High-risk operation, needs approval + red warning (HIGH)
    BLOCKED = "blocked"     # Absolutely forbidden, reject immediately


def compress_output(output: str, max_chars: int = 10000) -> str:
    """Truncate overly long tool output. Shared by ssh_bash / bash / service_exec."""
    if len(output) <= max_chars:
        return output
    truncated_count = len(output) - max_chars
    marker = f"\n\n... [truncated {truncated_count} characters] ...\n\n"
    remaining = max_chars - len(marker)
    half = remaining // 2
    return f"{output[:half]}{marker}{output[-half:]}"


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
        if ch == '\\' and i + 1 < len(cmd):
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
                if cmd[i:i + len(delim)] == delim:
                    parts.append(''.join(current).strip())
                    current = []
                    i += len(delim)
                    matched = True
                    break
            if matched:
                continue
        current.append(ch)
        i += 1
    parts.append(''.join(current).strip())
    return [p for p in parts if p]


def _split_compounds(cmd: str) -> list[str]:
    """Split on ``||``, ``&&``, ``;`` outside quotes."""
    return _split_outside_quotes(cmd, ["||", "&&", ";"])


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


# ═══════════════════════════════════════════
# Shell Safety (ssh_bash + bash shared)
# ═══════════════════════════════════════════

# Absolutely forbidden (never execute)
_BLOCKED_PATTERNS = [
    r"rm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\s*$",  # rm -rf /
    r"rm\s+(-[a-zA-Z]*)?r[a-zA-Z]*f[a-zA-Z]*\s+/\*",     # rm -rf /*
    r"rm\s+.*--no-preserve-root",                          # rm --no-preserve-root
    r":\(\)\s*\{",                                          # fork bomb
    r">\s*/dev/sd",                                         # redirect to block device
]

# Local-only blocked patterns (local=True)
# Only block privilege escalation and sensitive file access.
# Service commands (docker/kubectl/systemctl) go through normal
# DANGEROUS/WRITE/READ classification → approval flow.
_LOCAL_BLOCKED_PATTERNS = [
    r"\bsudo\b",
    r"\bsu\b\s",
    r"\.env\b",
    r"/etc/(shadow|passwd|sudoers)",
]

_LOCAL_BLOCKED_PREFIXES = [
    "sudo", "su ",
]

# Dangerous patterns (needs approval + red warning)
_DANGEROUS_PATTERNS = [
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

# Write patterns (needs approval, MEDIUM)
_WRITE_PATTERNS = [
    r"\bsed\s+.*-i\b",
    r"\bsed\s+.*--in-place\b",
    r"\bcurl\s+.*-X\s*(POST|PUT|DELETE|PATCH)\b",
    r"\bcurl\s+.*--request\s*(POST|PUT|DELETE|PATCH)\b",
    r"\bcurl\s+.*(-d\s|--data|--data-raw|--data-binary)",
    r"\bwget\s",
    r"\btee\s+\S",
    r"\b(mysql|mariadb|psql)\b.*\b(INSERT|UPDATE|DELETE|ALTER|CREATE|GRANT|REVOKE)\b",
]

# Read-only patterns for service CLIs (regex, case-insensitive)
_READ_PATTERNS = [
    r"\bredis-cli\b.*\b(GET|MGET|HGET|HGETALL|HMGET|HKEYS|HVALS|HLEN|HEXISTS)\b",
    r"\bredis-cli\b.*\b(LRANGE|LLEN|LINDEX)\b",
    r"\bredis-cli\b.*\b(SMEMBERS|SCARD|SISMEMBER|SRANDMEMBER)\b",
    r"\bredis-cli\b.*\b(ZRANGE|ZREVRANGE|ZCARD|ZSCORE|ZRANK|ZCOUNT)\b",
    r"\bredis-cli\b.*\b(KEYS|SCAN|TYPE|TTL|PTTL|EXISTS|DBSIZE|STRLEN|OBJECT|RANDOMKEY)\b",
    r"\bredis-cli\b.*\b(INFO|PING|TIME)\b",
    r"\bredis-cli\b.*\b(CONFIG\s+GET|CLIENT\s+LIST|SLOWLOG\s+(GET|LEN))\b",
    r"\bredis-cli\b.*\b(CLUSTER\s+(INFO|NODES)|MEMORY\s+(USAGE|STATS))\b",
    r"\bredis-cli\s+.*--(scan|bigkeys|stat|latency)\b",
    r"\b(mysql|mariadb)\b.*-e\s+[\"']\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b",
    r"\bpsql\b.*-c\s+[\"']\s*(SELECT|SHOW|EXPLAIN)\b",
    r"\bpsql\b\s+.*(-l|--list)\b",
    r"\betcdctl\s+(get|endpoint\s+(health|status)|member\s+list|alarm\s+list|version)\b",
    r"\brabbitmqctl\s+(status|cluster_status|list_queues|list_exchanges|list_bindings|list_connections|list_channels|list_consumers|list_users|list_vhosts|list_permissions)\b",
]

# SSH read-only command prefixes (whitelist)
_READ_PREFIXES = [
    "ls", "cat", "head", "tail", "less", "more", "grep", "awk", "sed",
    "echo", "nproc", "command",
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
    "xargs",
    "file", "stat", "wc", "sort", "uniq", "cut", "tr",
    "mount", "lsblk", "blkid", "fdisk -l",
    "nginx -t", "nginx -T",
    "supervisorctl status",
    "pm2 list", "pm2 ls", "pm2 status", "pm2 logs", "pm2 show", "pm2 info",
    "crontab -l",
]

# Local read-only command prefixes (aligned with SSH _READ_PREFIXES)
_LOCAL_READ_PREFIXES = [
    "ls", "cat", "head", "tail", "less", "more", "grep", "awk", "sed",
    "echo", "nproc", "command",
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
    "xargs",
    "file", "stat", "wc", "sort", "uniq", "cut", "tr",
    "mount", "lsblk", "blkid", "fdisk -l",
    "nginx -t", "nginx -T",
    "supervisorctl status",
    "pm2 list", "pm2 ls", "pm2 status", "pm2 logs", "pm2 show", "pm2 info",
    "crontab -l",
    # Local-specific
    "python", "python3",
    "bash", "sh",
    "jq",
]


class ShellSafety:
    @staticmethod
    def classify(command: str, local: bool = False) -> CommandType:
        """Classify a shell command. local=True enables stricter local execution policy."""
        cmd = command.strip()

        # 1. BLOCKED: universal dangerous patterns
        for pattern in _BLOCKED_PATTERNS:
            if re.search(pattern, cmd):
                return CommandType.BLOCKED

        # 1b. BLOCKED: local-only patterns
        if local:
            for pattern in _LOCAL_BLOCKED_PATTERNS:
                if re.search(pattern, cmd):
                    return CommandType.BLOCKED
            for prefix in _LOCAL_BLOCKED_PREFIXES:
                if cmd.startswith(prefix):
                    return CommandType.BLOCKED

        # 2. DANGEROUS
        for pattern in _DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return CommandType.DANGEROUS

        # 3. WRITE patterns
        for pattern in _WRITE_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return CommandType.WRITE

        # 4. Split compound commands then pipes — quote-aware
        read_prefixes = _LOCAL_READ_PREFIXES if local else _READ_PREFIXES

        sub_commands = _split_compounds(cmd)
        for sub_cmd in sub_commands:
            parts = _split_pipes(sub_cmd)
            for part in parts:
                if not part:
                    continue
                normalized_part = _strip_timeout_wrapper(part)
                is_read = any(normalized_part.startswith(prefix) for prefix in read_prefixes)
                if not is_read:
                    is_read = any(
                        re.search(p, normalized_part, re.IGNORECASE)
                        for p in _READ_PATTERNS
                    )
                if not is_read:
                    return CommandType.WRITE

        # 5. All parts in whitelist → READ
        return CommandType.READ


# ═══════════════════════════════════════════
# Service Safety (service_exec)
# ═══════════════════════════════════════════

def _classify_sql(command: str) -> CommandType:
    """Classify a SQL command."""
    cmd = command.strip()
    upper = cmd.upper()

    # READ: SELECT, SHOW, EXPLAIN, DESCRIBE/DESC, WITH...SELECT (CTE)
    if re.match(r"^(SELECT|SHOW|EXPLAIN|DESCRIBE|DESC)\b", upper):
        return CommandType.READ
    if re.match(r"^WITH\s+.*\bSELECT\b", upper, re.DOTALL):
        return CommandType.READ

    # DANGEROUS: DROP, TRUNCATE, DELETE without WHERE
    if re.match(r"^(DROP|TRUNCATE)\b", upper):
        return CommandType.DANGEROUS
    if re.match(r"^DELETE\b", upper) and "WHERE" not in upper:
        return CommandType.DANGEROUS

    # WRITE: INSERT, UPDATE, DELETE (with WHERE), CREATE, ALTER, GRANT, REVOKE
    if re.match(r"^(INSERT|UPDATE|DELETE|CREATE|ALTER|GRANT|REVOKE)\b", upper):
        return CommandType.WRITE

    # Default: WRITE (conservative)
    return CommandType.WRITE


_REDIS_READ = {
    "GET", "MGET", "HGET", "HGETALL", "HMGET", "HKEYS", "HVALS", "HLEN", "HEXISTS",
    "LRANGE", "LLEN", "LINDEX",
    "SMEMBERS", "SCARD", "SISMEMBER",
    "ZRANGE", "ZREVRANGE", "ZCARD", "ZSCORE", "ZRANK", "ZCOUNT",
    "KEYS", "SCAN", "TYPE", "TTL", "PTTL", "EXISTS", "DBSIZE", "STRLEN",
    "INFO", "PING", "TIME", "OBJECT", "RANDOMKEY", "MEMORY", "CLIENT", "SLOWLOG", "CLUSTER", "CONFIG",
}

_REDIS_DANGEROUS = {"FLUSHDB", "FLUSHALL", "SHUTDOWN", "DEBUG"}

_REDIS_WRITE = {
    "SET", "MSET", "DEL", "HSET", "HDEL",
    "LPUSH", "RPUSH", "LPOP", "RPOP",
    "SADD", "SREM", "ZADD", "ZREM",
    "EXPIRE", "PERSIST", "RENAME", "MOVE", "COPY",
    "INCR", "DECR", "APPEND", "SETEX", "SETNX",
}


def _classify_redis(command: str) -> CommandType:
    """Classify a Redis command."""
    parts = command.strip().split()
    if not parts:
        return CommandType.WRITE

    first = parts[0].upper()

    # Special: CONFIG SET → WRITE, CONFIG GET → READ
    if first == "CONFIG" and len(parts) >= 2:
        sub = parts[1].upper()
        if sub == "SET":
            return CommandType.WRITE
        if sub == "GET":
            return CommandType.READ

    if first in _REDIS_DANGEROUS:
        return CommandType.DANGEROUS
    if first in _REDIS_READ:
        return CommandType.READ
    if first in _REDIS_WRITE:
        return CommandType.WRITE

    # Default: WRITE
    return CommandType.WRITE


def _classify_prometheus(_command: str) -> CommandType:
    """PromQL is naturally read-only."""
    return CommandType.READ


_MONGO_READ = {
    "find", "count", "countdocuments", "listcollections", "listdatabases",
    "aggregate", "dbstats", "collstats", "explain", "distinct", "ping",
    "getmore", "serverstatus", "buildinfo", "connectionstatus",
}

_MONGO_DANGEROUS = {
    "dropdatabase", "drop", "dropindexes",
}

_MONGO_WRITE = {
    "insert", "update", "delete", "findandmodify",
    "createindexes", "create", "renamecollection",
}


def _classify_mongodb(command: str) -> CommandType:
    """Classify a MongoDB command document (JSON)."""
    import json

    try:
        cmd_doc = json.loads(command.strip())
    except (json.JSONDecodeError, TypeError):
        return CommandType.WRITE

    if not isinstance(cmd_doc, dict) or not cmd_doc:
        return CommandType.WRITE

    first_key = next(iter(cmd_doc)).lower()

    if first_key in _MONGO_DANGEROUS:
        return CommandType.DANGEROUS
    if first_key in _MONGO_READ:
        # aggregate with $out or $merge is a write
        if first_key == "aggregate":
            pipeline = cmd_doc.get("pipeline", cmd_doc.get("cursor", []))
            if isinstance(pipeline, list):
                for stage in pipeline:
                    if isinstance(stage, dict) and ("$out" in stage or "$merge" in stage):
                        return CommandType.WRITE
        return CommandType.READ
    if first_key in _MONGO_WRITE:
        return CommandType.WRITE

    # Default: WRITE (conservative)
    return CommandType.WRITE


def _classify_elasticsearch(command: str) -> CommandType:
    """Classify an Elasticsearch HTTP command."""
    cmd = command.strip()
    parts = cmd.split(None, 2)
    if not parts:
        return CommandType.WRITE

    method = parts[0].upper()
    path = parts[1] if len(parts) > 1 else ""

    if method == "GET" or method == "HEAD":
        return CommandType.READ

    if method == "DELETE":
        return CommandType.DANGEROUS

    # POST: _search, _count, _explain, _validate, _analyze, _cat are read-only
    if method == "POST":
        read_endpoints = ("_search", "_count", "_explain", "_validate", "_analyze", "_msearch")
        if any(ep in path for ep in read_endpoints):
            return CommandType.READ

    # POST/PUT to _doc, _bulk, _update, _reindex, _create → WRITE
    return CommandType.WRITE


def _classify_jenkins(command: str) -> CommandType:
    """Classify a Jenkins HTTP command."""
    cmd = command.strip()
    parts = cmd.split(None, 2)
    if not parts:
        return CommandType.WRITE

    method = parts[0].upper()
    path = parts[1] if len(parts) > 1 else ""

    if method in ("GET", "HEAD"):
        return CommandType.READ

    # POST: build → WRITE, stop/delete → DANGEROUS
    if method == "POST":
        if re.search(r"/(stop|delete|doDelete|disable)\b", path, re.IGNORECASE):
            return CommandType.DANGEROUS
        return CommandType.WRITE

    if method == "DELETE":
        return CommandType.DANGEROUS

    return CommandType.WRITE


def _classify_kettle(command: str) -> CommandType:
    """Classify a Kettle (Carte) HTTP command."""
    cmd = command.strip()
    parts = cmd.split(None, 2)
    if not parts:
        return CommandType.WRITE

    method = parts[0].upper()
    path = parts[1] if len(parts) > 1 else ""

    if method in ("GET", "HEAD"):
        # GET status/transStatus/jobStatus are read-only
        # GET start* is a write operation
        if re.search(r"/(start|run|execute)", path, re.IGNORECASE):
            return CommandType.WRITE
        # GET stop/remove are dangerous
        if re.search(r"/(stop|remove|clean)", path, re.IGNORECASE):
            return CommandType.DANGEROUS
        return CommandType.READ

    if method == "POST":
        if re.search(r"/(stop|remove|clean)", path, re.IGNORECASE):
            return CommandType.DANGEROUS
        if re.search(r"/(start|run|execute)", path, re.IGNORECASE):
            return CommandType.WRITE
        return CommandType.WRITE

    return CommandType.WRITE


_K8S_READ_SUBCOMMANDS = {
    "get", "describe", "logs", "top", "explain",
    "api-resources", "api-versions", "cluster-info",
    "version", "auth",
}

_K8S_DANGEROUS_SUBCOMMANDS = {
    "delete", "drain", "cordon", "taint",
}

_K8S_WRITE_SUBCOMMANDS = {
    "apply", "create", "patch", "replace", "set",
    "scale", "autoscale", "rollout",
    "label", "annotate", "uncordon",
    "edit", "expose", "run", "cp", "exec",
}

_K8S_BLOCKED_SUBCOMMANDS = {
    "proxy",
}


def _k8s_get_subcommand(rest: str) -> str | None:
    """Extract the first non-flag token from the command string after 'kubectl'."""
    for part in rest.split():
        if not part.startswith("-"):
            return part.lower()
    return None


def _classify_kubernetes(command: str) -> CommandType:
    """Classify a kubectl command."""
    cmd = command.strip()

    if cmd.startswith("kubectl "):
        rest = cmd[len("kubectl "):]
    elif cmd == "kubectl":
        return CommandType.READ
    else:
        return CommandType.WRITE

    subcommand = _k8s_get_subcommand(rest)
    if subcommand is None:
        return CommandType.WRITE

    if subcommand in _K8S_BLOCKED_SUBCOMMANDS:
        return CommandType.BLOCKED

    if subcommand in _K8S_DANGEROUS_SUBCOMMANDS:
        return CommandType.DANGEROUS

    # rollout: status/history → READ, undo/restart → DANGEROUS, others → WRITE
    if subcommand == "rollout":
        # Find the sub-subcommand after "rollout"
        found_rollout = False
        for part in rest.split():
            if part.startswith("-"):
                continue
            if not found_rollout:
                if part.lower() == "rollout":
                    found_rollout = True
                continue
            sub_sub = part.lower()
            if sub_sub in ("undo", "restart"):
                return CommandType.DANGEROUS
            if sub_sub in ("status", "history"):
                return CommandType.READ
            return CommandType.WRITE
        return CommandType.WRITE

    if subcommand in _K8S_READ_SUBCOMMANDS:
        return CommandType.READ

    if subcommand in _K8S_WRITE_SUBCOMMANDS:
        return CommandType.WRITE

    return CommandType.WRITE


_DOCKER_READ_SUBCOMMANDS = {
    "ps", "inspect", "logs", "top", "stats", "diff",
    "images", "version", "info", "port",
}
_DOCKER_WRITE_SUBCOMMANDS = {
    "start", "stop", "restart", "pause", "unpause", "exec", "pull",
}
_DOCKER_DANGEROUS_SUBCOMMANDS = {
    "rm", "rmi", "kill", "prune",
}


def _classify_docker(command: str) -> CommandType:
    """Classify a docker command."""
    cmd = command.strip()

    if cmd.startswith("docker "):
        rest = cmd[len("docker "):]
    elif cmd == "docker":
        return CommandType.READ
    else:
        return CommandType.WRITE

    parts = rest.split()
    if not parts:
        return CommandType.READ

    subcmd = parts[0].lower()

    # Handle compound subcommands: docker system prune
    if subcmd == "system" and len(parts) > 1:
        sub_sub = parts[1].lower()
        if sub_sub == "prune":
            return CommandType.DANGEROUS
        if sub_sub in ("info", "df", "events"):
            return CommandType.READ
        return CommandType.WRITE

    if subcmd in _DOCKER_DANGEROUS_SUBCOMMANDS:
        return CommandType.DANGEROUS

    if subcmd in _DOCKER_READ_SUBCOMMANDS:
        return CommandType.READ

    if subcmd in _DOCKER_WRITE_SUBCOMMANDS:
        return CommandType.WRITE

    return CommandType.WRITE


_SERVICE_CLASSIFIERS = {
    "postgresql": _classify_sql,
    "mysql": _classify_sql,
    "redis": _classify_redis,
    "prometheus": _classify_prometheus,
    "mongodb": _classify_mongodb,
    "elasticsearch": _classify_elasticsearch,
    "doris": _classify_sql,
    "starrocks": _classify_sql,
    "jenkins": _classify_jenkins,
    "kettle": _classify_kettle,
    "hive": _classify_sql,
    "kubernetes": _classify_kubernetes,
    "docker": _classify_docker,
}


class ServiceSafety:
    @staticmethod
    def classify(service_type: str, command: str) -> CommandType:
        """Classify a command by service type."""
        classifier = _SERVICE_CLASSIFIERS.get(service_type)
        if classifier is None:
            return CommandType.WRITE
        return classifier(command)
