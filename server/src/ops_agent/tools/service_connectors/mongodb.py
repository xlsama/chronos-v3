import json
import re

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

from src.lib.logger import get_logger
from src.ops_agent.tools.service_connectors.base import ServiceConnector, ServiceResult

log = get_logger(component="service_exec")

# Admin commands → fallback suggestions when permission denied (code 13)
_ADMIN_CMD_FALLBACKS: dict[str, str] = {
    "listdatabases": (
        "权限不足，无法执行 listDatabases（需要集群管理员权限）。\n"
        "降级方案：\n"
        '1. 在已知数据库上列出集合: {"listCollections": 1, "$db": "<数据库名>"}\n'
        '2. 查看数据库统计: {"dbStats": 1, "$db": "<数据库名>"}\n'
        '3. 查看当前用户权限: {"connectionStatus": 1}'
    ),
    "serverstatus": (
        "权限不足，无法执行 serverStatus（需要 clusterMonitor 角色）。\n"
        "降级方案：\n"
        '1. 查看数据库统计: {"dbStats": 1}\n'
        '2. 查看集合统计: {"collStats": "<集合名>"}\n'
        '3. 查看连接状态: {"connectionStatus": 1}'
    ),
    "replsetgetstatus": (
        "权限不足，无法执行 replSetGetStatus（需要 clusterMonitor 角色）。\n"
        "降级方案：\n"
        '1. 查看基本副本集信息: {"hello": 1}\n'
        '2. 验证连接可用性: {"ping": 1}'
    ),
    "currentop": (
        "权限不足，无法执行 currentOp。\n"
        "降级方案：\n"
        "1. 查看当前用户自己的操作: "
        '{"aggregate": 1, "pipeline": [{"$currentOp": {"ownOps": true}}], "cursor": {}}\n'
        '2. 查看连接状态: {"connectionStatus": 1}'
    ),
    "top": (
        "权限不足，无法执行 top（需要 clusterMonitor 角色）。\n"
        "降级方案：\n"
        '1. 查看集合统计: {"collStats": "<集合名>"}\n'
        '2. 查看数据库统计: {"dbStats": 1}'
    ),
}

_GENERIC_AUTH_FALLBACK = (
    "权限不足，当前用户没有执行此操作的权限。\n"
    "建议：\n"
    '1. 查看当前用户角色和权限: {"connectionStatus": 1}\n'
    '2. 尝试在指定数据库上操作，在命令中添加 "$db": "<数据库名>"\n'
    "3. 如果是集群管理命令，尝试使用数据库级别的替代命令"
)

_PARSE_ERROR_HINT = (
    "无法解析命令。支持的格式：\n"
    '1. JSON 命令: {"serverStatus": 1}\n'
    "2. Shell 命令: db.serverStatus()\n"
    '3. 集合查询: db.users.find({"name": "test"})\n'
    '4. runCommand: db.runCommand({"connectionStatus": 1})\n'
    "5. show 命令: show collections, show dbs"
)

# ── JS-to-JSON conversion ──

# Match unquoted keys in JS object literals: { key: ..., $key: ... }
_JS_KEY_RE = re.compile(
    r"(?<=[{,])\s*([$a-zA-Z_][$a-zA-Z0-9_]*)\s*:",
)


def _js_to_json(text: str) -> dict:
    """Parse a JavaScript-style object literal into a Python dict.

    Handles: unquoted keys, $-prefixed keys, single-quoted strings,
    JS booleans (true/false) and null.
    """
    s = text.strip()

    # First try standard JSON
    try:
        result = json.loads(s)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Replace single-quoted strings with double-quoted
    # Simple approach: replace ' with " when used as string delimiters
    converted = ""
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "'":
            # Find matching closing single quote
            converted += '"'
            i += 1
            while i < len(s) and s[i] != "'":
                if s[i] == '"':
                    converted += '\\"'
                elif s[i] == "\\":
                    converted += s[i : i + 2]
                    i += 1
                else:
                    converted += s[i]
                i += 1
            converted += '"'
            i += 1
        else:
            converted += ch
            i += 1

    # Quote unquoted keys
    converted = _JS_KEY_RE.sub(r'"\1":', converted)

    # Replace JS literals
    converted = re.sub(r"\btrue\b", "true", converted)
    converted = re.sub(r"\bfalse\b", "false", converted)
    converted = re.sub(r"\bnull\b", "null", converted)

    try:
        result = json.loads(converted)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    raise ValueError(f"Cannot parse as JSON object: {text}")


def _js_to_json_str(text: str) -> str:
    """Parse JS-style object literal and return as JSON string."""
    return json.dumps(_js_to_json(text))


# ── Shell command → JSON command document translation ──

_SHOW_COMMANDS: dict[str, str] = {
    "show collections": '{"listCollections": 1}',
    "show tables": '{"listCollections": 1}',
    "show dbs": '{"listDatabases": 1}',
    "show databases": '{"listDatabases": 1}',
    "show users": '{"usersInfo": 1}',
    "show roles": '{"rolesInfo": 1}',
    "show profile": '{"profile": -1}',
}

# Known admin/database-level commands that take no collection argument
_KNOWN_ADMIN_COMMANDS: set[str] = {
    "serverStatus",
    "connectionStatus",
    "buildInfo",
    "ping",
    "hello",
    "hostInfo",
    "isMaster",
    "dbStats",
    "listCollections",
    "listDatabases",
    "usersInfo",
    "rolesInfo",
    "replSetGetStatus",
    "getCmdLineOpts",
    "getLog",
    "currentOp",
    "collStats",
    "validate",
    "top",
    "features",
    "whatsmyuri",
    "profile",
    "getParameter",
    "setParameter",
    "compact",
    "reIndex",
    "connPoolStats",
    "shardingState",
    "dataSize",
    "dbHash",
}

# Case-insensitive lookup: lowercase → canonical name
_ADMIN_CMD_LOOKUP: dict[str, str] = {name.lower(): name for name in _KNOWN_ADMIN_COMMANDS}

_DB_STATS_RE = re.compile(r"^db\.stats\s*\(\s*\)\s*$")

_DB_METHOD_RE = re.compile(
    r"^db\.(\w+)\."
    r"(find|findOne|count|countDocuments|estimatedDocumentCount|stats|drop|"
    r"aggregate|getIndexes|createIndex|distinct|"
    r"insertOne|insertMany|updateOne|updateMany|deleteOne|deleteMany|"
    r"findOneAndUpdate|findOneAndDelete|findOneAndReplace|replaceOne)"
    r"\s*\((.*)\)\s*$",
    re.DOTALL,
)

# db.runCommand({...}) or db.adminCommand({...})
_DB_RUN_CMD_RE = re.compile(
    r"^db\.(runCommand|adminCommand)\s*\(\s*(.*)\s*\)\s*$",
    re.DOTALL,
)

# db.<adminCommand>() or db.<adminCommand>({options})
_DB_ADMIN_CMD_RE = re.compile(
    r"^db\.(\w+)\s*\(\s*(.*?)\s*\)\s*$",
    re.DOTALL,
)

# db.getCollection("name").<method>(...)
_DB_GET_COLLECTION_RE = re.compile(
    r"""^db\.getCollection\s*\(\s*["'](\w+)["']\s*\)\s*\.\s*"""
    r"(find|findOne|count|countDocuments|estimatedDocumentCount|stats|drop|"
    r"aggregate|getIndexes|createIndex|distinct|"
    r"insertOne|insertMany|updateOne|updateMany|deleteOne|deleteMany|"
    r"findOneAndUpdate|findOneAndDelete|findOneAndReplace|replaceOne)"
    r"\s*\((.*)\)\s*$",
    re.DOTALL,
)

# Chained property access: strip .field1.field2 after a closing paren
_CHAINED_ACCESS_RE = re.compile(
    r"^(.*\))\s*(\.\w+(?:\.\w+)*)\s*$",
)


def _translate_shell_command(command: str) -> str | None:
    """Translate a MongoDB shell command to a JSON command string.

    Returns a JSON string if matched, or None to fall through to normal JSON parsing.
    """
    cmd = command.strip()
    lower = cmd.lower()

    # ── "show ..." commands ──
    result = _SHOW_COMMANDS.get(lower)
    if result is not None:
        return result

    # ── db.stats() ──
    if _DB_STATS_RE.match(cmd):
        return '{"dbStats": 1}'

    # ── Chained property access: db.serverStatus().connections → db.serverStatus() ──
    m_chain = _CHAINED_ACCESS_RE.match(cmd)
    if m_chain:
        base_cmd = m_chain.group(1).strip()
        # Recursively translate the base command
        translated = _translate_shell_command(base_cmd)
        if translated is not None:
            return translated

    # ── db.runCommand({...}) / db.adminCommand({...}) ──
    m_run = _DB_RUN_CMD_RE.match(cmd)
    if m_run:
        method_name = m_run.group(1)
        args_str = m_run.group(2).strip()
        if args_str:
            try:
                doc = _js_to_json(args_str)
                if method_name == "adminCommand":
                    doc["$db"] = "admin"
                return json.dumps(doc)
            except (ValueError, json.JSONDecodeError):
                pass
        return None

    # ── db.getCollection("name").<method>(...) ──
    m_gc = _DB_GET_COLLECTION_RE.match(cmd)
    if m_gc:
        collection, method, args_str = m_gc.group(1), m_gc.group(2), m_gc.group(3).strip()
        return _translate_collection_method(collection, method, args_str)

    # ── db.<collection>.<method>(...) ──
    m_col = _DB_METHOD_RE.match(cmd)
    if m_col:
        collection, method, args_str = m_col.group(1), m_col.group(2), m_col.group(3).strip()
        return _translate_collection_method(collection, method, args_str)

    # ── db.<adminCommand>() or db.<adminCommand>({options}) ──
    m_admin = _DB_ADMIN_CMD_RE.match(cmd)
    if m_admin:
        cmd_name = m_admin.group(1)
        args_str = m_admin.group(2).strip()
        canonical = _ADMIN_CMD_LOOKUP.get(cmd_name.lower())
        if canonical:
            doc: dict = {canonical: 1}
            if args_str:
                try:
                    opts = _js_to_json(args_str)
                    doc.update(opts)
                except (ValueError, json.JSONDecodeError):
                    pass
            return json.dumps(doc)

    return None


def _translate_collection_method(collection: str, method: str, args_str: str) -> str:
    """Translate a db.<collection>.<method>(...) call to a JSON command string."""
    if method in ("find", "findOne"):
        doc: dict = {"find": collection, "filter": {}}
        if method == "findOne":
            doc["limit"] = 1
        if args_str:
            try:
                parsed = json.loads(f"[{args_str}]")
                if len(parsed) >= 1 and isinstance(parsed[0], dict):
                    doc["filter"] = parsed[0]
                if len(parsed) >= 2 and isinstance(parsed[1], dict):
                    doc["projection"] = parsed[1]
            except json.JSONDecodeError:
                try:
                    parsed = _js_to_json(f"[{args_str}]" if "," in args_str else args_str)
                    if isinstance(parsed, dict):
                        doc["filter"] = parsed
                except (ValueError, json.JSONDecodeError):
                    pass
        return json.dumps(doc)

    if method in ("count", "countDocuments", "estimatedDocumentCount"):
        doc = {"count": collection}
        if args_str:
            try:
                f = json.loads(args_str)
                if isinstance(f, dict):
                    doc["query"] = f
            except json.JSONDecodeError:
                try:
                    f = _js_to_json(args_str)
                    if isinstance(f, dict):
                        doc["query"] = f
                except (ValueError, json.JSONDecodeError):
                    pass
        return json.dumps(doc)

    if method == "stats":
        return json.dumps({"collStats": collection})

    if method == "getIndexes":
        return json.dumps({"listIndexes": collection})

    if method == "createIndex":
        doc = {"createIndexes": collection, "indexes": []}
        if args_str:
            try:
                parsed = json.loads(f"[{args_str}]")
                keys = parsed[0] if len(parsed) >= 1 else {}
                options = parsed[1] if len(parsed) >= 2 and isinstance(parsed[1], dict) else {}
                index_doc = {"key": keys, "name": "_".join(f"{k}_{v}" for k, v in keys.items())}
                index_doc.update(options)
                doc["indexes"] = [index_doc]
            except json.JSONDecodeError:
                pass
        return json.dumps(doc)

    if method == "aggregate":
        doc = {"aggregate": collection, "cursor": {}}
        if args_str:
            try:
                pipeline = json.loads(args_str)
                if isinstance(pipeline, list):
                    doc["pipeline"] = pipeline
            except json.JSONDecodeError:
                doc["pipeline"] = []
        else:
            doc["pipeline"] = []
        return json.dumps(doc)

    if method == "distinct":
        doc = {"distinct": collection, "key": ""}
        if args_str:
            try:
                parsed = json.loads(f"[{args_str}]")
                if len(parsed) >= 1 and isinstance(parsed[0], str):
                    doc["key"] = parsed[0]
                if len(parsed) >= 2 and isinstance(parsed[1], dict):
                    doc["query"] = parsed[1]
            except json.JSONDecodeError:
                # Try bare string field name
                field = args_str.strip("\"' ")
                if field:
                    doc["key"] = field
        return json.dumps(doc)

    if method == "drop":
        return json.dumps({"drop": collection})

    # Write operations: insertOne, insertMany, updateOne, updateMany, deleteOne, deleteMany
    if method == "insertOne":
        doc = {"insert": collection, "documents": []}
        if args_str:
            try:
                d = json.loads(args_str)
                if isinstance(d, dict):
                    doc["documents"] = [d]
            except json.JSONDecodeError:
                try:
                    d = _js_to_json(args_str)
                    doc["documents"] = [d]
                except (ValueError, json.JSONDecodeError):
                    pass
        return json.dumps(doc)

    if method == "insertMany":
        doc = {"insert": collection, "documents": []}
        if args_str:
            try:
                d = json.loads(args_str)
                if isinstance(d, list):
                    doc["documents"] = d
            except json.JSONDecodeError:
                pass
        return json.dumps(doc)

    if method in ("updateOne", "updateMany"):
        doc = {"update": collection, "updates": []}
        if args_str:
            try:
                parsed = json.loads(f"[{args_str}]")
                if len(parsed) >= 2:
                    update_doc = {"q": parsed[0], "u": parsed[1], "multi": method == "updateMany"}
                    doc["updates"] = [update_doc]
            except json.JSONDecodeError:
                pass
        return json.dumps(doc)

    if method in ("deleteOne", "deleteMany"):
        doc = {"delete": collection, "deletes": []}
        if args_str:
            try:
                f = json.loads(args_str)
                if isinstance(f, dict):
                    doc["deletes"] = [{"q": f, "limit": 0 if method == "deleteMany" else 1}]
            except json.JSONDecodeError:
                try:
                    f = _js_to_json(args_str)
                    doc["deletes"] = [{"q": f, "limit": 0 if method == "deleteMany" else 1}]
                except (ValueError, json.JSONDecodeError):
                    pass
        return json.dumps(doc)

    if method in ("findOneAndUpdate", "findOneAndDelete", "findOneAndReplace"):
        doc = {"findAndModify": collection}
        if args_str:
            try:
                parsed = json.loads(f"[{args_str}]")
                if len(parsed) >= 1:
                    doc["query"] = parsed[0]
                if method == "findOneAndDelete":
                    doc["remove"] = True
                elif len(parsed) >= 2:
                    if method == "findOneAndReplace":
                        doc["update"] = parsed[1]
                    else:
                        doc["update"] = parsed[1]
            except json.JSONDecodeError:
                pass
        return json.dumps(doc)

    if method == "replaceOne":
        doc = {"update": collection, "updates": []}
        if args_str:
            try:
                parsed = json.loads(f"[{args_str}]")
                if len(parsed) >= 2:
                    doc["updates"] = [{"q": parsed[0], "u": parsed[1], "multi": False}]
            except json.JSONDecodeError:
                pass
        return json.dumps(doc)

    # Fallback: return find command for unrecognized method
    return json.dumps({"find": collection, "filter": {}})


class MongoDBConnector(ServiceConnector):
    service_type = "mongodb"

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        database: str,
        auth_source: str | None = None,
    ):
        self._database = database
        # Build connection URI
        if username and password:
            self._uri = f"mongodb://{username}:{password}@{host}:{port}"
            if auth_source:
                self._uri += f"?authSource={auth_source}"
        else:
            self._uri = f"mongodb://{host}:{port}"
        self._client: AsyncIOMotorClient | None = None

    def _get_client(self) -> AsyncIOMotorClient:
        if self._client is None:
            # Mask password in URI for logging
            safe_uri = (
                re.sub(r"://[^:]+:[^@]+@", "://***:***@", self._uri)
                if "@" in self._uri
                else self._uri
            )
            log.info("Creating client", uri=safe_uri)
            self._client = AsyncIOMotorClient(self._uri, serverSelectionTimeoutMS=5000)
        return self._client

    async def execute(self, command: str) -> ServiceResult:
        translated = _translate_shell_command(command)
        raw = translated if translated is not None else command.strip()

        try:
            cmd_doc = json.loads(raw)
        except json.JSONDecodeError:
            # Try JS-style parsing as last resort
            try:
                cmd_doc = _js_to_json(raw)
            except (ValueError, json.JSONDecodeError):
                return ServiceResult(success=False, output="", error=_PARSE_ERROR_HINT)

        if not isinstance(cmd_doc, dict) or not cmd_doc:
            return ServiceResult(success=False, output="", error="命令必须是非空 JSON 对象")

        # Allow agent to target a specific database via "$db" key
        target_db = cmd_doc.pop("$db", None) or self._database

        cmd_str = str(cmd_doc)
        log.info("Executing command", command_len=len(cmd_str), database=target_db)
        log.debug("Executing command", command=cmd_str)
        try:
            client = self._get_client()
            db = client[target_db]
            result = await db.command(cmd_doc)
            output = json.dumps(result, indent=2, default=str, ensure_ascii=False)
            log.info("Command result", output_len=len(output))
            return ServiceResult(success=True, output=output)
        except OperationFailure as e:
            log.warning("MongoDB OperationFailure", code=e.code, error=str(e))
            if e.code == 13:  # Unauthorized
                first_key = next(iter(cmd_doc), "").lower()
                hint = _ADMIN_CMD_FALLBACKS.get(first_key, _GENERIC_AUTH_FALLBACK)
                return ServiceResult(
                    success=False,
                    output="",
                    error=f"OperationFailure: {e}\n\n[降级提示] {hint}",
                )
            return ServiceResult(success=False, output="", error=f"OperationFailure: {e}")
        except Exception as e:
            log.error("Execute failed", error=str(e))
            return ServiceResult(success=False, output="", error=f"{type(e).__name__}: {e}")

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
