"""Unit tests for MongoDB connector: shell command translation & JS-to-JSON conversion."""

import json

import pytest

from src.ops_agent.tools.service_connectors.mongodb import (
    _js_to_json,
    _translate_shell_command,
)
from src.ops_agent.tools.tool_classifier import CommandType, ServiceSafety


# ═══════════════════════════════════════════
# JS-to-JSON conversion
# ═══════════════════════════════════════════


class TestJsToJson:
    def test_standard_json_passthrough(self):
        assert _js_to_json('{"ping": 1}') == {"ping": 1}

    def test_unquoted_keys(self):
        assert _js_to_json("{connectionStatus: 1}") == {"connectionStatus": 1}

    def test_dollar_prefixed_keys(self):
        assert _js_to_json("{$match: {status: 1}}") == {"$match": {"status": 1}}

    def test_single_quoted_strings(self):
        assert _js_to_json("{'name': 'test'}") == {"name": "test"}

    def test_nested_objects(self):
        result = _js_to_json("{serverStatus: 1, repl: {oplog: 1}}")
        assert result == {"serverStatus": 1, "repl": {"oplog": 1}}

    def test_array_values(self):
        result = _js_to_json('{pipeline: [{"$match": {}}]}')
        assert result == {"pipeline": [{"$match": {}}]}

    def test_boolean_and_null(self):
        result = _js_to_json("{verbose: true, debug: false, extra: null}")
        assert result == {"verbose": True, "debug": False, "extra": None}

    def test_mixed_styles(self):
        result = _js_to_json("{connectionStatus: 1, showPrivileges: true}")
        assert result == {"connectionStatus": 1, "showPrivileges": True}

    def test_invalid_input_raises(self):
        with pytest.raises(ValueError):
            _js_to_json("not a json object at all")

    def test_numeric_values(self):
        result = _js_to_json("{limit: 10, skip: 0}")
        assert result == {"limit": 10, "skip": 0}


# ═══════════════════════════════════════════
# Show commands
# ═══════════════════════════════════════════


class TestShowCommands:
    def test_show_collections(self):
        result = json.loads(_translate_shell_command("show collections"))
        assert result == {"listCollections": 1}

    def test_show_dbs(self):
        result = json.loads(_translate_shell_command("show dbs"))
        assert result == {"listDatabases": 1}

    def test_show_databases(self):
        result = json.loads(_translate_shell_command("show databases"))
        assert result == {"listDatabases": 1}

    def test_show_users(self):
        result = json.loads(_translate_shell_command("show users"))
        assert result == {"usersInfo": 1}

    def test_show_roles(self):
        result = json.loads(_translate_shell_command("show roles"))
        assert result == {"rolesInfo": 1}

    def test_case_insensitive(self):
        result = json.loads(_translate_shell_command("SHOW COLLECTIONS"))
        assert result == {"listCollections": 1}


# ═══════════════════════════════════════════
# db.stats()
# ═══════════════════════════════════════════


class TestDbStats:
    def test_db_stats(self):
        result = json.loads(_translate_shell_command("db.stats()"))
        assert result == {"dbStats": 1}

    def test_db_stats_with_spaces(self):
        result = json.loads(_translate_shell_command("db.stats(  )"))
        assert result == {"dbStats": 1}


# ═══════════════════════════════════════════
# Admin commands: db.<command>()
# ═══════════════════════════════════════════


class TestAdminCommands:
    def test_server_status(self):
        result = json.loads(_translate_shell_command("db.serverStatus()"))
        assert result == {"serverStatus": 1}

    def test_connection_status(self):
        result = json.loads(_translate_shell_command("db.connectionStatus()"))
        assert result == {"connectionStatus": 1}

    def test_build_info(self):
        result = json.loads(_translate_shell_command("db.buildInfo()"))
        assert result == {"buildInfo": 1}

    def test_ping(self):
        result = json.loads(_translate_shell_command("db.ping()"))
        assert result == {"ping": 1}

    def test_hello(self):
        result = json.loads(_translate_shell_command("db.hello()"))
        assert result == {"hello": 1}

    def test_host_info(self):
        result = json.loads(_translate_shell_command("db.hostInfo()"))
        assert result == {"hostInfo": 1}

    def test_is_master(self):
        result = json.loads(_translate_shell_command("db.isMaster()"))
        assert result == {"isMaster": 1}

    def test_list_collections(self):
        result = json.loads(_translate_shell_command("db.listCollections()"))
        assert result == {"listCollections": 1}

    def test_list_databases(self):
        result = json.loads(_translate_shell_command("db.listDatabases()"))
        assert result == {"listDatabases": 1}

    def test_repl_set_get_status(self):
        result = json.loads(_translate_shell_command("db.replSetGetStatus()"))
        assert result == {"replSetGetStatus": 1}

    def test_get_cmd_line_opts(self):
        result = json.loads(_translate_shell_command("db.getCmdLineOpts()"))
        assert result == {"getCmdLineOpts": 1}

    def test_current_op(self):
        result = json.loads(_translate_shell_command("db.currentOp()"))
        assert result == {"currentOp": 1}

    def test_admin_command_with_options(self):
        result = json.loads(_translate_shell_command("db.serverStatus({repl: 1})"))
        assert result == {"serverStatus": 1, "repl": 1}

    def test_case_insensitive_admin(self):
        """Admin command lookup is case-insensitive."""
        result = json.loads(_translate_shell_command("db.serverstatus()"))
        assert "serverStatus" in result


# ═══════════════════════════════════════════
# db.runCommand({...}) / db.adminCommand({...})
# ═══════════════════════════════════════════


class TestRunCommand:
    def test_run_command_json(self):
        result = json.loads(_translate_shell_command('db.runCommand({"connectionStatus": 1})'))
        assert result == {"connectionStatus": 1}

    def test_run_command_js_style(self):
        result = json.loads(_translate_shell_command("db.runCommand({connectionStatus: 1})"))
        assert result == {"connectionStatus": 1}

    def test_run_command_nested(self):
        cmd = 'db.runCommand({aggregate: "users", pipeline: [{"$match": {}}], cursor: {}})'
        result = json.loads(_translate_shell_command(cmd))
        assert result["aggregate"] == "users"
        assert result["pipeline"] == [{"$match": {}}]

    def test_admin_command(self):
        result = json.loads(_translate_shell_command("db.adminCommand({listDatabases: 1})"))
        assert result["listDatabases"] == 1
        assert result["$db"] == "admin"

    def test_admin_command_json_style(self):
        result = json.loads(_translate_shell_command('db.adminCommand({"serverStatus": 1})'))
        assert result["serverStatus"] == 1
        assert result["$db"] == "admin"


# ═══════════════════════════════════════════
# db.getCollection("name").<method>(...)
# ═══════════════════════════════════════════


class TestGetCollection:
    def test_get_collection_find(self):
        result = json.loads(_translate_shell_command('db.getCollection("users").find({})'))
        assert result == {"find": "users", "filter": {}}

    def test_get_collection_count(self):
        result = json.loads(_translate_shell_command("db.getCollection('logs').countDocuments()"))
        assert result == {"count": "logs"}

    def test_get_collection_aggregate(self):
        cmd = 'db.getCollection("events").aggregate([{"$match": {"type": "error"}}])'
        result = json.loads(_translate_shell_command(cmd))
        assert result["aggregate"] == "events"
        assert result["pipeline"] == [{"$match": {"type": "error"}}]


# ═══════════════════════════════════════════
# Chained property access
# ═══════════════════════════════════════════


class TestChainedAccess:
    def test_server_status_connections(self):
        """db.serverStatus().connections → translates db.serverStatus()"""
        result = json.loads(_translate_shell_command("db.serverStatus().connections"))
        assert result == {"serverStatus": 1}

    def test_deep_chain(self):
        """db.serverStatus().repl.primary → translates db.serverStatus()"""
        result = json.loads(_translate_shell_command("db.serverStatus().repl.primary"))
        assert result == {"serverStatus": 1}

    def test_chain_on_collection(self):
        """db.users.stats().ns → translates db.users.stats()"""
        result = json.loads(_translate_shell_command("db.users.stats().ns"))
        assert result == {"collStats": "users"}


# ═══════════════════════════════════════════
# Collection methods
# ═══════════════════════════════════════════


class TestCollectionMethods:
    def test_find_empty(self):
        result = json.loads(_translate_shell_command("db.users.find()"))
        assert result == {"find": "users", "filter": {}}

    def test_find_with_filter(self):
        result = json.loads(_translate_shell_command('db.users.find({"name": "test"})'))
        assert result == {"find": "users", "filter": {"name": "test"}}

    def test_find_with_projection(self):
        result = json.loads(_translate_shell_command('db.users.find({}, {"name": 1})'))
        assert result == {"find": "users", "filter": {}, "projection": {"name": 1}}

    def test_find_one(self):
        result = json.loads(_translate_shell_command('db.users.findOne({"_id": 1})'))
        assert result["find"] == "users"
        assert result["limit"] == 1
        assert result["filter"] == {"_id": 1}

    def test_count(self):
        result = json.loads(_translate_shell_command("db.logs.count()"))
        assert result == {"count": "logs"}

    def test_count_with_filter(self):
        result = json.loads(_translate_shell_command('db.logs.count({"level": "error"})'))
        assert result == {"count": "logs", "query": {"level": "error"}}

    def test_count_documents(self):
        result = json.loads(_translate_shell_command("db.users.countDocuments()"))
        assert result == {"count": "users"}

    def test_aggregate(self):
        cmd = 'db.orders.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}])'
        result = json.loads(_translate_shell_command(cmd))
        assert result["aggregate"] == "orders"
        assert len(result["pipeline"]) == 1

    def test_aggregate_empty(self):
        result = json.loads(_translate_shell_command("db.orders.aggregate()"))
        assert result == {"aggregate": "orders", "cursor": {}, "pipeline": []}

    def test_stats(self):
        result = json.loads(_translate_shell_command("db.users.stats()"))
        assert result == {"collStats": "users"}

    def test_get_indexes(self):
        result = json.loads(_translate_shell_command("db.users.getIndexes()"))
        assert result == {"listIndexes": "users"}

    def test_distinct(self):
        result = json.loads(_translate_shell_command('db.users.distinct("status")'))
        assert result == {"distinct": "users", "key": "status"}

    def test_drop(self):
        result = json.loads(_translate_shell_command("db.temp.drop()"))
        assert result == {"drop": "temp"}

    def test_insert_one(self):
        result = json.loads(_translate_shell_command('db.users.insertOne({"name": "test"})'))
        assert result == {"insert": "users", "documents": [{"name": "test"}]}

    def test_delete_one(self):
        result = json.loads(_translate_shell_command('db.users.deleteOne({"_id": 1})'))
        assert result["delete"] == "users"
        assert result["deletes"][0]["q"] == {"_id": 1}
        assert result["deletes"][0]["limit"] == 1

    def test_delete_many(self):
        result = json.loads(_translate_shell_command('db.logs.deleteMany({"old": true})'))
        assert result["delete"] == "logs"
        assert result["deletes"][0]["limit"] == 0


# ═══════════════════════════════════════════
# Unrecognized commands return None
# ═══════════════════════════════════════════


class TestUnrecognized:
    def test_random_text(self):
        assert _translate_shell_command("hello world") is None

    def test_unknown_db_method(self):
        """Unknown method on db that isn't in admin commands."""
        assert _translate_shell_command("db.unknownXyz123()") is None

    def test_empty_string(self):
        assert _translate_shell_command("") is None


# ═══════════════════════════════════════════
# Classifier integration with new translator
# ═══════════════════════════════════════════


class TestClassifierMongoDB:
    def test_json_ping_read(self):
        assert ServiceSafety.classify("mongodb", '{"ping": 1}') is CommandType.READ

    def test_shell_server_status_read(self):
        assert ServiceSafety.classify("mongodb", "db.serverStatus()") is CommandType.READ

    def test_shell_connection_status_read(self):
        assert ServiceSafety.classify("mongodb", "db.connectionStatus()") is CommandType.READ

    def test_shell_run_command_read(self):
        assert (
            ServiceSafety.classify("mongodb", "db.runCommand({connectionStatus: 1})")
            is CommandType.READ
        )

    def test_chained_server_status_read(self):
        assert (
            ServiceSafety.classify("mongodb", "db.serverStatus().connections") is CommandType.READ
        )

    def test_show_collections_read(self):
        assert ServiceSafety.classify("mongodb", "show collections") is CommandType.READ

    def test_find_read(self):
        assert ServiceSafety.classify("mongodb", "db.users.find({})") is CommandType.READ

    def test_drop_dangerous(self):
        assert ServiceSafety.classify("mongodb", "db.temp.drop()") is CommandType.DANGEROUS

    def test_insert_write(self):
        assert (
            ServiceSafety.classify("mongodb", 'db.users.insertOne({"name": "test"})')
            is CommandType.WRITE
        )

    def test_js_style_json_read(self):
        assert ServiceSafety.classify("mongodb", "{serverStatus: 1}") is CommandType.READ
