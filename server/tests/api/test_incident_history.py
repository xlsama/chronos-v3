"""Tests for /api/incident-history endpoints."""

import uuid

from tests.api.conftest import create_incident_history_in_db


class TestListIncidentHistory:
    async def test_list_empty(self, client):
        resp = await client.get("/api/incident-history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_with_data(self, client, db_session):
        await create_incident_history_in_db(db_session, title="MySQL outage")
        await create_incident_history_in_db(db_session, title="Redis timeout")

        resp = await client.get("/api/incident-history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_pagination(self, client, db_session):
        for i in range(5):
            await create_incident_history_in_db(db_session, title=f"History {i}")

        resp = await client.get(
            "/api/incident-history", params={"page": 1, "page_size": 2}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2


class TestGetIncidentHistory:
    async def test_get(self, client, db_session):
        record = await create_incident_history_in_db(db_session, title="Test outage")

        resp = await client.get(f"/api/incident-history/{record.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test outage"
        assert data["id"] == str(record.id)

    async def test_get_not_found(self, client):
        resp = await client.get(f"/api/incident-history/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestDeleteIncidentHistory:
    async def test_delete(self, client, db_session):
        record = await create_incident_history_in_db(db_session)

        resp = await client.delete(f"/api/incident-history/{record.id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        get_resp = await client.get(f"/api/incident-history/{record.id}")
        assert get_resp.status_code == 404

    async def test_delete_not_found(self, client):
        resp = await client.delete(f"/api/incident-history/{uuid.uuid4()}")
        assert resp.status_code == 404
