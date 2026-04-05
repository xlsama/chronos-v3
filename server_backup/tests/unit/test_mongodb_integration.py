"""Integration tests for MongoDB connector against a real MongoDB instance.

Requires: docker compose -f server/tests/agent/docker-compose.agent.yml up -d mongo-target
Skips automatically if MongoDB is not reachable on localhost:17017.
"""

import asyncio

import pytest

MONGO_HOST = "localhost"
MONGO_PORT = 17017


def _mongo_available() -> bool:
    """Check if MongoDB is reachable."""
    import socket

    try:
        s = socket.create_connection((MONGO_HOST, MONGO_PORT), timeout=2)
        s.close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _mongo_available(),
    reason=f"MongoDB not available on {MONGO_HOST}:{MONGO_PORT}",
)


@pytest.fixture
def connector():
    from src.ops_agent.tools.service_connectors.mongodb import MongoDBConnector

    c = MongoDBConnector(
        host=MONGO_HOST,
        port=MONGO_PORT,
        username=None,
        password=None,
        database="test",
    )
    yield c
    asyncio.get_event_loop().run_until_complete(c.close())


# ═══════════════════════════════════════════
# Basic connectivity
# ═══════════════════════════════════════════


class TestBasicConnectivity:
    async def test_ping_json(self, connector):
        result = await connector.execute('{"ping": 1}')
        assert result.success
        assert '"ok"' in result.output

    async def test_ping_shell(self, connector):
        result = await connector.execute("db.ping()")
        assert result.success
        assert '"ok"' in result.output


# ═══════════════════════════════════════════
# Admin commands (shell syntax)
# ═══════════════════════════════════════════


class TestAdminCommands:
    async def test_server_status(self, connector):
        result = await connector.execute("db.serverStatus()")
        assert result.success
        assert '"host"' in result.output or '"version"' in result.output

    async def test_server_status_chained(self, connector):
        """Chained access should succeed (strips .connections, runs serverStatus)."""
        result = await connector.execute("db.serverStatus().connections")
        assert result.success
        assert '"ok"' in result.output

    async def test_connection_status(self, connector):
        result = await connector.execute("db.connectionStatus()")
        assert result.success
        assert '"authInfo"' in result.output or '"ok"' in result.output

    async def test_build_info(self, connector):
        result = await connector.execute("db.buildInfo()")
        assert result.success
        assert '"version"' in result.output

    async def test_hello(self, connector):
        result = await connector.execute("db.hello()")
        assert result.success
        assert result.output  # Non-empty response

    async def test_host_info(self, connector):
        result = await connector.execute("db.hostInfo()")
        assert result.success


# ═══════════════════════════════════════════
# db.runCommand()
# ═══════════════════════════════════════════


class TestRunCommand:
    async def test_run_command_json(self, connector):
        result = await connector.execute('db.runCommand({"connectionStatus": 1})')
        assert result.success
        assert '"ok"' in result.output

    async def test_run_command_js_style(self, connector):
        result = await connector.execute("db.runCommand({connectionStatus: 1})")
        assert result.success
        assert '"ok"' in result.output

    async def test_run_command_build_info(self, connector):
        result = await connector.execute("db.runCommand({buildInfo: 1})")
        assert result.success
        assert '"version"' in result.output

    async def test_run_command_ping(self, connector):
        result = await connector.execute("db.runCommand({ping: 1})")
        assert result.success


# ═══════════════════════════════════════════
# Show commands
# ═══════════════════════════════════════════


class TestShowCommands:
    async def test_show_collections(self, connector):
        result = await connector.execute("show collections")
        assert result.success

    async def test_show_databases(self, connector):
        """show dbs requires admin db; verify it runs without parse errors."""
        result = await connector.execute("show dbs")
        # May fail with permission error on non-admin db, but should NOT be a parse error
        if not result.success:
            assert "listDatabases" in result.error
            assert "JSON 解析" not in result.error


# ═══════════════════════════════════════════
# Collection operations (CRUD)
# ═══════════════════════════════════════════


class TestCollectionOperations:
    async def test_insert_and_find(self, connector):
        # Insert a document
        result = await connector.execute(
            'db.test_collection.insertOne({"name": "chronos_test", "value": 42})'
        )
        assert result.success

        # Find the document
        result = await connector.execute(
            'db.test_collection.find({"name": "chronos_test"})'
        )
        assert result.success
        assert "chronos_test" in result.output

        # Count documents
        result = await connector.execute(
            'db.test_collection.countDocuments({"name": "chronos_test"})'
        )
        assert result.success

        # Clean up
        result = await connector.execute(
            'db.test_collection.deleteMany({"name": "chronos_test"})'
        )
        assert result.success

    async def test_aggregate(self, connector):
        # Insert test data
        await connector.execute(
            'db.agg_test.insertOne({"category": "A", "amount": 10})'
        )
        await connector.execute(
            'db.agg_test.insertOne({"category": "A", "amount": 20})'
        )

        # Aggregate
        result = await connector.execute(
            'db.agg_test.aggregate([{"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}])'
        )
        assert result.success

        # Clean up
        await connector.execute('db.agg_test.deleteMany({})')

    async def test_collection_stats(self, connector):
        # Ensure collection exists
        await connector.execute('db.stats_test.insertOne({"x": 1})')

        result = await connector.execute("db.stats_test.stats()")
        assert result.success

        # Clean up
        await connector.execute("db.stats_test.drop()")

    async def test_list_indexes(self, connector):
        await connector.execute('db.idx_test.insertOne({"x": 1})')

        result = await connector.execute("db.idx_test.getIndexes()")
        assert result.success
        assert "_id" in result.output  # Default _id index

        await connector.execute("db.idx_test.drop()")


# ═══════════════════════════════════════════
# JS-style JSON (no shell prefix)
# ═══════════════════════════════════════════


class TestJsStyleJson:
    async def test_js_style_ping(self, connector):
        result = await connector.execute("{ping: 1}")
        assert result.success

    async def test_js_style_build_info(self, connector):
        result = await connector.execute("{buildInfo: 1}")
        assert result.success


# ═══════════════════════════════════════════
# Error handling
# ═══════════════════════════════════════════


class TestErrorHandling:
    async def test_invalid_command_shows_hint(self, connector):
        result = await connector.execute("this is not a valid command")
        assert not result.success
        assert "支持的格式" in result.error

    async def test_empty_command(self, connector):
        result = await connector.execute("   ")
        assert not result.success

    async def test_invalid_json_shows_hint(self, connector):
        result = await connector.execute("{invalid json !!!")
        assert not result.success
        assert "支持的格式" in result.error
