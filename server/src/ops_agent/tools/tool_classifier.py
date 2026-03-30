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
# Shell Safety (ssh_bash + bash shared)
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
# Block sensitive file access only. sudo/su go through normal classification.
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

# Shell metacharacter patterns — command substitution and redirection escalate to WRITE
_CMD_SUBSTITUTION_RE = regex.compile(r"\$\(|`")
_REDIRECT_WRITE_RE = regex.compile(r"\d*>{1,2}\s*(?!/dev/null\b)(?!&)\S")
_HEREDOC_RE = regex.compile(r'<<-?\s*\\?[\'"]?\w+')

# Read-only patterns for service CLIs — pre-compiled, IGNORECASE
# Redis-cli patterns consolidated into single alternation
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
_LOCAL_READ_PREFIXES = [
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
    # Local-specific
    "jq",
]


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
        #    Split compound commands (&&, ||, ;) then pipes (|).
        #    For each part: strip timeout/sudo, then classify the inner command.
        #    Return the highest severity across all parts.
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


# ═══════════════════════════════════════════
# Service Safety (service_exec)
# ═══════════════════════════════════════════

# Pre-compiled SQL classification patterns
_SQL_READ_RE = regex.compile(r"^(SELECT|SHOW|EXPLAIN|DESCRIBE|DESC|USE|SET)\b")
_SQL_CTE_READ_RE = regex.compile(r"^WITH\s+.*\bSELECT\b", regex.DOTALL)
_SQL_DANGEROUS_RE = regex.compile(r"^(DROP|TRUNCATE)\b")
_SQL_DELETE_RE = regex.compile(r"^DELETE\b")
_SQL_WRITE_RE = regex.compile(r"^(INSERT|UPDATE|DELETE|CREATE|ALTER|GRANT|REVOKE)\b")


def _classify_single_sql(stmt: str) -> CommandType:
    """Classify a single SQL statement (no semicolons)."""
    upper = stmt.strip().upper()
    if not upper:
        return CommandType.READ

    # SET GLOBAL / SET PERSIST affect server config → WRITE
    if upper.startswith("SET") and ("GLOBAL" in upper or "PERSIST" in upper):
        return CommandType.WRITE
    if _SQL_READ_RE.match(upper):
        return CommandType.READ
    if _SQL_CTE_READ_RE.match(upper):
        return CommandType.READ
    if _SQL_DANGEROUS_RE.match(upper):
        return CommandType.DANGEROUS
    if _SQL_DELETE_RE.match(upper) and "WHERE" not in upper:
        return CommandType.DANGEROUS
    if _SQL_WRITE_RE.match(upper):
        return CommandType.WRITE
    return CommandType.WRITE


def _classify_sql(command: str) -> CommandType:
    """Classify a SQL command. Handles multi-statement (;-separated)."""
    cmd = command.strip().rstrip(";")
    statements = [s.strip() for s in cmd.split(";") if s.strip()]
    if not statements:
        return CommandType.WRITE

    worst = CommandType.READ
    for stmt in statements:
        level = _classify_single_sql(stmt)
        if level in (CommandType.DANGEROUS, CommandType.BLOCKED):
            return level
        if level == CommandType.WRITE:
            worst = CommandType.WRITE
    return worst


_REDIS_READ = {
    "GET",
    "MGET",
    "HGET",
    "HGETALL",
    "HMGET",
    "HKEYS",
    "HVALS",
    "HLEN",
    "HEXISTS",
    "LRANGE",
    "LLEN",
    "LINDEX",
    "LPOS",
    "SMEMBERS",
    "SCARD",
    "SISMEMBER",
    "SRANDMEMBER",
    "SINTER",
    "SUNION",
    "SDIFF",
    "ZRANGE",
    "ZREVRANGE",
    "ZCARD",
    "ZSCORE",
    "ZRANK",
    "ZCOUNT",
    "KEYS",
    "SCAN",
    "HSCAN",
    "SSCAN",
    "ZSCAN",
    "TYPE",
    "TTL",
    "PTTL",
    "EXISTS",
    "DBSIZE",
    "STRLEN",
    "INFO",
    "PING",
    "TIME",
    "OBJECT",
    "RANDOMKEY",
    "MEMORY",
    "CLIENT",
    "SLOWLOG",
    "CLUSTER",
    "CONFIG",
    "ACL",
    "COMMAND",
    "SELECT",
    "ECHO",
    "WAIT",
    "DUMP",
    "PUBSUB",
    "SUBSCRIBE",
    "PSUBSCRIBE",
    "XLEN",
    "XRANGE",
    "XREVRANGE",
    "XINFO",
    "XREAD",
    "GEORADIUS",
    "GEOPOS",
    "GEODIST",
    "GEOSEARCH",
    "GEOHASH",
    "PFCOUNT",
    "BITCOUNT",
    "BITPOS",
    "GETBIT",
    "GETRANGE",
}

_REDIS_DANGEROUS = {"FLUSHDB", "FLUSHALL", "SHUTDOWN", "DEBUG"}

_REDIS_WRITE = {
    "SET",
    "MSET",
    "DEL",
    "HSET",
    "HDEL",
    "LPUSH",
    "RPUSH",
    "LPOP",
    "RPOP",
    "SADD",
    "SREM",
    "ZADD",
    "ZREM",
    "EXPIRE",
    "PERSIST",
    "RENAME",
    "MOVE",
    "COPY",
    "INCR",
    "DECR",
    "APPEND",
    "SETEX",
    "SETNX",
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

    # Special: ACL SETUSER/DELUSER/SAVE/LOAD → WRITE, others (LIST/WHOAMI/GETUSER/CAT/LOG) → READ
    if first == "ACL" and len(parts) >= 2:
        sub = parts[1].upper()
        if sub in ("SETUSER", "DELUSER", "SAVE", "LOAD"):
            return CommandType.WRITE
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
    "find",
    "count",
    "countdocuments",
    "listcollections",
    "listdatabases",
    "listindexes",
    "aggregate",
    "dbstats",
    "collstats",
    "explain",
    "distinct",
    "ping",
    "getmore",
    "serverstatus",
    "buildinfo",
    "connectionstatus",
    "hello",
    "ismaster",
    "currentop",
    "validate",
    "getlog",
    "replsetgetstatus",
    "hostinfo",
    "getcmdlineopts",
}

_MONGO_DANGEROUS = {
    "dropdatabase",
    "drop",
    "dropindexes",
}

_MONGO_WRITE = {
    "insert",
    "update",
    "delete",
    "findandmodify",
    "createindexes",
    "create",
    "renamecollection",
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


# Pre-compiled Jenkins/Kettle path patterns
_JENKINS_DANGEROUS_PATH_RE = regex.compile(r"/(stop|delete|doDelete|disable)\b", regex.IGNORECASE)
_KETTLE_START_RE = regex.compile(r"/(start|run|execute)", regex.IGNORECASE)
_KETTLE_STOP_RE = regex.compile(r"/(stop|remove|clean)", regex.IGNORECASE)


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
        if _JENKINS_DANGEROUS_PATH_RE.search(path):
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
        if _KETTLE_START_RE.search(path):
            return CommandType.WRITE
        # GET stop/remove are dangerous
        if _KETTLE_STOP_RE.search(path):
            return CommandType.DANGEROUS
        return CommandType.READ

    if method == "POST":
        if _KETTLE_STOP_RE.search(path):
            return CommandType.DANGEROUS
        if _KETTLE_START_RE.search(path):
            return CommandType.WRITE
        return CommandType.WRITE

    return CommandType.WRITE


_K8S_READ_SUBCOMMANDS = {
    "get",
    "describe",
    "logs",
    "top",
    "explain",
    "api-resources",
    "api-versions",
    "cluster-info",
    "version",
    "auth",
}

_K8S_DANGEROUS_SUBCOMMANDS = {
    "delete",
    "drain",
    "cordon",
    "taint",
}

_K8S_WRITE_SUBCOMMANDS = {
    "apply",
    "create",
    "patch",
    "replace",
    "set",
    "scale",
    "autoscale",
    "rollout",
    "label",
    "annotate",
    "uncordon",
    "edit",
    "expose",
    "run",
    "cp",
    "exec",
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
        rest = cmd[len("kubectl ") :]
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
    "ps",
    "inspect",
    "logs",
    "top",
    "stats",
    "diff",
    "images",
    "version",
    "info",
    "port",
}
_DOCKER_WRITE_SUBCOMMANDS = {
    "start",
    "stop",
    "restart",
    "pause",
    "unpause",
    "exec",
    "pull",
}
_DOCKER_DANGEROUS_SUBCOMMANDS = {
    "rm",
    "rmi",
    "kill",
    "prune",
}


def _classify_docker(command: str) -> CommandType:
    """Classify a docker command."""
    cmd = command.strip()

    if cmd.startswith("docker "):
        rest = cmd[len("docker ") :]
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
