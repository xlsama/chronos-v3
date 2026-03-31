"""Tests for /api/services endpoints."""

import uuid

from tests.factories import make_service_payload


class TestCreateService:
    async def test_create_service(self, client):
        payload = make_service_payload()
        resp = await client.post("/api/services", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["service_type"] == "mysql"
        assert data["host"] == payload["host"]
        assert data["port"] == payload["port"]
        assert data["has_password"] is True
        assert data["status"] == "unknown"
        assert "password" not in data
        assert "encrypted_password" not in data

    async def test_create_service_without_password(self, client):
        payload = make_service_payload(password=None)
        resp = await client.post("/api/services", json=payload)
        assert resp.status_code == 200
        assert resp.json()["has_password"] is False

    async def test_create_service_invalid_type(self, client):
        payload = make_service_payload(service_type="invalid_db")
        resp = await client.post("/api/services", json=payload)
        assert resp.status_code == 422

    async def test_create_service_all_valid_types(self, client):
        types = [
            "mysql", "postgresql", "redis", "prometheus", "mongodb",
            "elasticsearch", "doris", "starrocks", "jenkins", "kettle",
            "hive", "kubernetes", "docker",
        ]
        for stype in types:
            payload = make_service_payload(service_type=stype)
            resp = await client.post("/api/services", json=payload)
            assert resp.status_code == 200, f"Failed for type: {stype}"
            assert resp.json()["service_type"] == stype

    async def test_create_service_duplicate_name(self, client):
        payload = make_service_payload()
        resp1 = await client.post("/api/services", json=payload)
        assert resp1.status_code == 200

        # DB unique constraint — raises IntegrityError (unhandled → 500)
        resp2 = await client.post("/api/services", json=payload)
        assert resp2.status_code >= 400


class TestListServices:
    async def test_list_services_empty(self, client):
        resp = await client.get("/api/services")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_services_pagination(self, client):
        for _ in range(3):
            await client.post("/api/services", json=make_service_payload())

        resp = await client.get("/api/services", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    async def test_list_services_filter_type(self, client):
        await client.post("/api/services", json=make_service_payload(service_type="mysql"))
        await client.post("/api/services", json=make_service_payload(service_type="redis"))

        resp = await client.get("/api/services", params={"type": "redis"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["service_type"] == "redis"


class TestGetService:
    async def test_get_service(self, client):
        create_resp = await client.post("/api/services", json=make_service_payload())
        service_id = create_resp.json()["id"]

        resp = await client.get(f"/api/services/{service_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == service_id

    async def test_get_service_not_found(self, client):
        resp = await client.get(f"/api/services/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateService:
    async def test_update_service(self, client):
        create_resp = await client.post("/api/services", json=make_service_payload())
        service_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/services/{service_id}", json={"description": "updated"}
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "updated"

    async def test_update_service_config(self, client):
        create_resp = await client.post("/api/services", json=make_service_payload())
        service_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/services/{service_id}", json={"config": {"database": "testdb"}}
        )
        assert resp.status_code == 200
        assert resp.json()["config"] == {"database": "testdb"}

    async def test_update_service_not_found(self, client):
        resp = await client.patch(
            f"/api/services/{uuid.uuid4()}", json={"description": "x"}
        )
        assert resp.status_code == 404


class TestDeleteService:
    async def test_delete_service(self, client):
        create_resp = await client.post("/api/services", json=make_service_payload())
        service_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/services/{service_id}")
        assert resp.status_code == 204

        get_resp = await client.get(f"/api/services/{service_id}")
        assert get_resp.status_code == 404

    async def test_delete_service_not_found(self, client):
        resp = await client.delete(f"/api/services/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestBatchCreateServices:
    async def test_batch_create(self, client):
        items = [make_service_payload() for _ in range(3)]
        resp = await client.post("/api/services/batch", json={"items": items})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 3
        assert data["skipped"] == 0

    async def test_batch_skip_duplicates(self, client):
        payload = make_service_payload()
        await client.post("/api/services", json=payload)

        items = [payload, make_service_payload()]
        resp = await client.post("/api/services/batch", json={"items": items})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 1
        assert data["skipped"] == 1


class TestTestService:
    async def test_test_service_inline(self, client):
        resp = await client.post(
            "/api/services/test-inline",
            json={"service_type": "mysql", "host": "192.168.99.99", "port": 3306},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "message" in data

    async def test_test_service_by_id(self, client):
        create_resp = await client.post("/api/services", json=make_service_payload())
        service_id = create_resp.json()["id"]

        resp = await client.post(f"/api/services/{service_id}/test")
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data

    async def test_test_service_not_found(self, client):
        resp = await client.post(f"/api/services/{uuid.uuid4()}/test")
        assert resp.status_code == 404
