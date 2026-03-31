"""Tests for /api/connections endpoints."""

from tests.factories import make_server_payload, make_service_payload


class TestTestAllConnections:
    async def test_test_all_empty(self, client):
        resp = await client.post("/api/connections/test-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["success_count"] == 0
        assert data["failure_count"] == 0
        assert data["results"] == []

    async def test_test_all_with_data(self, client):
        # Create some servers and services
        await client.post("/api/servers", json=make_server_payload())
        await client.post("/api/services", json=make_service_payload())

        resp = await client.post("/api/connections/test-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["results"]) == 2

        # All should fail since there's no real service
        types = {r["type"] for r in data["results"]}
        assert "server" in types
        assert "service" in types

    async def test_test_all_result_structure(self, client):
        await client.post("/api/servers", json=make_server_payload())

        resp = await client.post("/api/connections/test-all")
        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert "id" in result
        assert "name" in result
        assert "type" in result
        assert "success" in result
        assert "message" in result
