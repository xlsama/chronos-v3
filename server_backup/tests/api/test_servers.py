"""Tests for /api/servers endpoints."""

import uuid

from tests.factories import make_server_payload


class TestCreateServer:
    async def test_create_server(self, client):
        payload = make_server_payload()
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["host"] == payload["host"]
        assert data["port"] == payload["port"]
        assert data["username"] == payload["username"]
        assert data["auth_method"] == "password"
        assert data["status"] == "unknown"
        assert "id" in data
        # Password should not be exposed
        assert "password" not in data
        assert "encrypted_password" not in data

    async def test_create_server_duplicate_name(self, client):
        payload = make_server_payload()
        resp1 = await client.post("/api/servers", json=payload)
        assert resp1.status_code == 200

        resp2 = await client.post("/api/servers", json=payload)
        assert resp2.status_code == 422

    async def test_create_server_missing_host(self, client):
        payload = make_server_payload(host="")
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 422

    async def test_create_server_with_bastion(self, client):
        payload = make_server_payload(
            bastion_host="10.0.0.1",
            bastion_port=22,
            bastion_username="jump",
            bastion_password="jumppass",
        )
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_bastion"] is True
        assert data["bastion_host"] == "10.0.0.1"

    async def test_create_server_with_private_key(self, client):
        payload = make_server_payload(password=None, private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----")
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 200
        assert resp.json()["auth_method"] == "private_key"


class TestListServers:
    async def test_list_servers_empty(self, client):
        resp = await client.get("/api/servers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_servers_pagination(self, client):
        # Create 3 servers
        for i in range(3):
            await client.post("/api/servers", json=make_server_payload())

        resp = await client.get("/api/servers", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 2


class TestGetServer:
    async def test_get_server(self, client):
        create_resp = await client.post("/api/servers", json=make_server_payload())
        server_id = create_resp.json()["id"]

        resp = await client.get(f"/api/servers/{server_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == server_id

    async def test_get_server_not_found(self, client):
        resp = await client.get(f"/api/servers/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateServer:
    async def test_update_server_name(self, client):
        create_resp = await client.post("/api/servers", json=make_server_payload())
        server_id = create_resp.json()["id"]

        resp = await client.patch(f"/api/servers/{server_id}", json={"name": "new-name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"

    async def test_update_server_partial(self, client):
        payload = make_server_payload()
        create_resp = await client.post("/api/servers", json=payload)
        server_id = create_resp.json()["id"]
        original_host = create_resp.json()["host"]

        resp = await client.patch(
            f"/api/servers/{server_id}", json={"description": "updated desc"}
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "updated desc"
        assert resp.json()["host"] == original_host

    async def test_update_server_not_found(self, client):
        resp = await client.patch(f"/api/servers/{uuid.uuid4()}", json={"name": "x"})
        assert resp.status_code == 404


class TestDeleteServer:
    async def test_delete_server(self, client):
        create_resp = await client.post("/api/servers", json=make_server_payload())
        server_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/servers/{server_id}")
        assert resp.status_code == 204

        get_resp = await client.get(f"/api/servers/{server_id}")
        assert get_resp.status_code == 404

    async def test_delete_server_not_found(self, client):
        resp = await client.delete(f"/api/servers/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestBatchCreateServers:
    async def test_batch_create(self, client):
        items = [make_server_payload() for _ in range(3)]
        resp = await client.post("/api/servers/batch", json={"items": items})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 3
        assert data["skipped"] == 0

    async def test_batch_create_skip_duplicates(self, client):
        payload = make_server_payload()
        await client.post("/api/servers", json=payload)

        items = [payload, make_server_payload()]
        resp = await client.post("/api/servers/batch", json={"items": items})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 1
        assert data["skipped"] == 1


class TestTestServer:
    async def test_test_server_inline(self, client):
        resp = await client.post(
            "/api/servers/test-inline",
            json={"host": "192.168.99.99", "port": 22, "username": "root"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "message" in data

    async def test_test_server_by_id(self, client):
        create_resp = await client.post("/api/servers", json=make_server_payload())
        server_id = create_resp.json()["id"]

        resp = await client.post(f"/api/servers/{server_id}/test")
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "message" in data

    async def test_test_server_not_found(self, client):
        resp = await client.post(f"/api/servers/{uuid.uuid4()}/test")
        assert resp.status_code == 404
