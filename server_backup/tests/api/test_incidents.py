"""Tests for /api/incidents endpoints."""

import uuid

from tests.api.conftest import create_incident_in_db, create_message_in_db
from tests.factories import make_incident_payload


class TestCreateIncident:
    async def test_create_incident(self, client):
        payload = make_incident_payload()
        resp = await client.post("/api/incidents", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == payload["description"]
        assert data["status"] == "open"
        assert data["severity"] == "P3"
        assert data["is_archived"] is False
        assert "id" in data

    async def test_create_incident_with_severity(self, client):
        for severity in ["P0", "P1", "P2", "P3"]:
            payload = make_incident_payload(severity=severity)
            resp = await client.post("/api/incidents", json=payload)
            assert resp.status_code == 200
            assert resp.json()["severity"] == severity


class TestListIncidents:
    async def test_list_incidents_empty(self, client):
        resp = await client.get("/api/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_incidents(self, client):
        for _ in range(3):
            await client.post("/api/incidents", json=make_incident_payload())

        resp = await client.get("/api/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    async def test_list_incidents_pagination(self, client):
        for _ in range(3):
            await client.post("/api/incidents", json=make_incident_payload())

        resp = await client.get("/api/incidents", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    async def test_list_incidents_filter_status(self, client, db_session):
        await create_incident_in_db(db_session, status="open")
        await create_incident_in_db(db_session, status="investigating")

        resp = await client.get("/api/incidents", params={"status": "investigating"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "investigating"

    async def test_list_incidents_filter_severity(self, client, db_session):
        await create_incident_in_db(db_session, severity="P0")
        await create_incident_in_db(db_session, severity="P3")

        resp = await client.get("/api/incidents", params={"severity": "P0"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["severity"] == "P0"

    async def test_archived_excluded_from_list(self, client):
        create_resp = await client.post("/api/incidents", json=make_incident_payload())
        incident_id = create_resp.json()["id"]

        await client.post(f"/api/incidents/{incident_id}/archive")

        resp = await client.get("/api/incidents")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestGetIncident:
    async def test_get_incident(self, client):
        create_resp = await client.post("/api/incidents", json=make_incident_payload())
        incident_id = create_resp.json()["id"]

        resp = await client.get(f"/api/incidents/{incident_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == incident_id

    async def test_get_incident_not_found(self, client):
        resp = await client.get(f"/api/incidents/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestGetMessages:
    async def test_get_messages_empty(self, client, db_session):
        incident = await create_incident_in_db(db_session)

        resp = await client.get(f"/api/incidents/{incident.id}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_messages(self, client, db_session):
        incident = await create_incident_in_db(db_session)
        await create_message_in_db(
            db_session, incident.id, event_type="thinking", content="analyzing..."
        )
        await create_message_in_db(
            db_session, incident.id, event_type="tool_use", content="ssh_bash"
        )

        resp = await client.get(f"/api/incidents/{incident.id}/messages")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2


class TestGetEvents:
    async def test_get_events(self, client, db_session):
        incident = await create_incident_in_db(db_session)
        await create_message_in_db(
            db_session,
            incident.id,
            event_type="thinking",
            content="analyzing...",
        )

        resp = await client.get(f"/api/incidents/{incident.id}/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        assert events[0]["event_type"] == "thinking"
        assert "data" in events[0]
        assert "timestamp" in events[0]


class TestSendUserMessage:
    async def test_send_user_message(self, client, db_session):
        incident = await create_incident_in_db(db_session)

        resp = await client.post(
            f"/api/incidents/{incident.id}/messages",
            json={"content": "help me debug this"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["event_type"] == "user_message"
        assert data["content"] == "help me debug this"

    async def test_send_user_message_not_found(self, client):
        resp = await client.post(
            f"/api/incidents/{uuid.uuid4()}/messages",
            json={"content": "hello"},
        )
        assert resp.status_code == 404


class TestConfirmResolution:
    async def test_confirm_resolution(self, client, db_session):
        incident = await create_incident_in_db(
            db_session, status="investigating", thread_id="test-thread"
        )

        resp = await client.post(f"/api/incidents/{incident.id}/confirm-resolution")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_confirm_resolution_wrong_status(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="open")

        resp = await client.post(f"/api/incidents/{incident.id}/confirm-resolution")
        assert resp.status_code == 400

    async def test_confirm_resolution_not_found(self, client):
        resp = await client.post(f"/api/incidents/{uuid.uuid4()}/confirm-resolution")
        assert resp.status_code == 404


class TestInterruptIncident:
    async def test_interrupt_incident(self, client, db_session):
        incident = await create_incident_in_db(
            db_session, status="investigating", thread_id="test-thread"
        )

        resp = await client.post(f"/api/incidents/{incident.id}/interrupt")
        assert resp.status_code == 200

    async def test_interrupt_wrong_status(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="open")

        resp = await client.post(f"/api/incidents/{incident.id}/interrupt")
        assert resp.status_code == 400

    async def test_interrupt_not_found(self, client):
        resp = await client.post(f"/api/incidents/{uuid.uuid4()}/interrupt")
        assert resp.status_code == 404


class TestStopIncident:
    async def test_stop_incident(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="investigating")

        resp = await client.post(f"/api/incidents/{incident.id}/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    async def test_stop_incident_open(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="open")

        resp = await client.post(f"/api/incidents/{incident.id}/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    async def test_stop_already_stopped(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="stopped")

        resp = await client.post(f"/api/incidents/{incident.id}/stop")
        assert resp.status_code == 400

    async def test_stop_already_resolved(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="resolved")

        resp = await client.post(f"/api/incidents/{incident.id}/stop")
        assert resp.status_code == 400

    async def test_stop_not_found(self, client):
        resp = await client.post(f"/api/incidents/{uuid.uuid4()}/stop")
        assert resp.status_code == 404


class TestArchiveIncident:
    async def test_archive_incident(self, client):
        create_resp = await client.post("/api/incidents", json=make_incident_payload())
        incident_id = create_resp.json()["id"]

        resp = await client.post(f"/api/incidents/{incident_id}/archive")
        assert resp.status_code == 200
        assert resp.json()["is_archived"] is True

    async def test_archive_not_found(self, client):
        resp = await client.post(f"/api/incidents/{uuid.uuid4()}/archive")
        assert resp.status_code == 404
