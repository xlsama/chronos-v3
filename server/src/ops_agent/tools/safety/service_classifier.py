"""Service 命令安全分类器 —— 对数据库/中间件/容器编排命令进行风险分级。"""

import regex

from .shell_classifier import CommandType

# ═══════════════════════════════════════════
# SQL (PostgreSQL, MySQL, Doris, StarRocks, Hive)
# ═══════════════════════════════════════════

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


# ═══════════════════════════════════════════
# Redis
# ═══════════════════════════════════════════

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

    # Special: ACL SETUSER/DELUSER/SAVE/LOAD → WRITE, others → READ
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

    return CommandType.WRITE


# ═══════════════════════════════════════════
# Prometheus
# ═══════════════════════════════════════════


def _classify_prometheus(_command: str) -> CommandType:
    """PromQL is naturally read-only."""
    return CommandType.READ


# ═══════════════════════════════════════════
# MongoDB
# ═══════════════════════════════════════════

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
    "usersinfo",
    "rolesinfo",
}

_MONGO_DANGEROUS = {"dropdatabase", "drop", "dropindexes"}

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
    """Classify a MongoDB command document (JSON) or shell command."""
    import json

    from src.ops_agent.tools.service_connectors.mongodb import (
        _js_to_json,
        _translate_shell_command,
    )

    translated = _translate_shell_command(command)
    raw = translated if translated is not None else command.strip()

    try:
        cmd_doc = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        try:
            cmd_doc = _js_to_json(raw)
        except (ValueError, json.JSONDecodeError, TypeError):
            return CommandType.WRITE

    if not isinstance(cmd_doc, dict) or not cmd_doc:
        return CommandType.WRITE

    first_key = next(iter(cmd_doc)).lower()

    if first_key in _MONGO_DANGEROUS:
        return CommandType.DANGEROUS
    if first_key in _MONGO_READ:
        if first_key == "aggregate":
            pipeline = cmd_doc.get("pipeline", cmd_doc.get("cursor", []))
            if isinstance(pipeline, list):
                for stage in pipeline:
                    if isinstance(stage, dict) and ("$out" in stage or "$merge" in stage):
                        return CommandType.WRITE
        return CommandType.READ
    if first_key in _MONGO_WRITE:
        return CommandType.WRITE

    return CommandType.WRITE


# ═══════════════════════════════════════════
# Elasticsearch
# ═══════════════════════════════════════════


def _classify_elasticsearch(command: str) -> CommandType:
    """Classify an Elasticsearch HTTP command."""
    cmd = command.strip()
    parts = cmd.split(None, 2)
    if not parts:
        return CommandType.WRITE

    method = parts[0].upper()
    path = parts[1] if len(parts) > 1 else ""

    if method in ("GET", "HEAD"):
        return CommandType.READ

    if method == "DELETE":
        return CommandType.DANGEROUS

    if method == "POST":
        read_endpoints = ("_search", "_count", "_explain", "_validate", "_analyze", "_msearch")
        if any(ep in path for ep in read_endpoints):
            return CommandType.READ

    return CommandType.WRITE


# ═══════════════════════════════════════════
# Jenkins
# ═══════════════════════════════════════════

_JENKINS_DANGEROUS_PATH_RE = regex.compile(r"/(stop|delete|doDelete|disable)\b", regex.IGNORECASE)


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

    if method == "POST":
        if _JENKINS_DANGEROUS_PATH_RE.search(path):
            return CommandType.DANGEROUS
        return CommandType.WRITE

    if method == "DELETE":
        return CommandType.DANGEROUS

    return CommandType.WRITE


# ═══════════════════════════════════════════
# Kettle (Carte)
# ═══════════════════════════════════════════

_KETTLE_START_RE = regex.compile(r"/(start|run|execute)", regex.IGNORECASE)
_KETTLE_STOP_RE = regex.compile(r"/(stop|remove|clean)", regex.IGNORECASE)


def _classify_kettle(command: str) -> CommandType:
    """Classify a Kettle (Carte) HTTP command."""
    cmd = command.strip()
    parts = cmd.split(None, 2)
    if not parts:
        return CommandType.WRITE

    method = parts[0].upper()
    path = parts[1] if len(parts) > 1 else ""

    if method in ("GET", "HEAD"):
        if _KETTLE_START_RE.search(path):
            return CommandType.WRITE
        if _KETTLE_STOP_RE.search(path):
            return CommandType.DANGEROUS
        return CommandType.READ

    if method == "POST":
        if _KETTLE_STOP_RE.search(path):
            return CommandType.DANGEROUS
        return CommandType.WRITE

    return CommandType.WRITE


# ═══════════════════════════════════════════
# Kubernetes
# ═══════════════════════════════════════════

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
_K8S_DANGEROUS_SUBCOMMANDS = {"delete", "drain", "cordon", "taint"}
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
_K8S_BLOCKED_SUBCOMMANDS = {"proxy"}


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

    if subcommand == "rollout":
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


# ═══════════════════════════════════════════
# Docker
# ═══════════════════════════════════════════

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
_DOCKER_WRITE_SUBCOMMANDS = {"start", "stop", "restart", "pause", "unpause", "exec", "pull"}
_DOCKER_DANGEROUS_SUBCOMMANDS = {"rm", "rmi", "kill", "prune"}


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


# ═══════════════════════════════════════════
# Service classifier registry
# ═══════════════════════════════════════════

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
