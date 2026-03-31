"""Tests for /api/approvals endpoints."""

import uuid

from tests.api.conftest import create_approval_in_db, create_incident_in_db


class TestGetApproval:
    async def test_get_approval(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="investigating")
        approval = await create_approval_in_db(db_session, incident.id)

        resp = await client.get(f"/api/approvals/{approval.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(approval.id)
        assert data["tool_name"] == "ssh_bash"
        assert data["risk_level"] == "HIGH"
        assert data["decision"] is None

    async def test_get_approval_not_found(self, client):
        resp = await client.get(f"/api/approvals/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestDecideApproval:
    async def test_decide_approved(self, client, db_session):
        incident = await create_incident_in_db(
            db_session, status="investigating", thread_id="test-thread"
        )
        approval = await create_approval_in_db(db_session, incident.id)

        resp = await client.post(
            f"/api/approvals/{approval.id}/decide",
            json={"decision": "approved", "decided_by": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "approved"
        assert data["decided_by"] == "admin"
        assert data["decided_at"] is not None

    async def test_decide_rejected(self, client, db_session):
        incident = await create_incident_in_db(
            db_session, status="investigating", thread_id="test-thread"
        )
        approval = await create_approval_in_db(db_session, incident.id)

        resp = await client.post(
            f"/api/approvals/{approval.id}/decide",
            json={"decision": "rejected", "decided_by": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "rejected"

    async def test_decide_supplemented(self, client, db_session):
        incident = await create_incident_in_db(
            db_session, status="investigating", thread_id="test-thread"
        )
        approval = await create_approval_in_db(db_session, incident.id)

        resp = await client.post(
            f"/api/approvals/{approval.id}/decide",
            json={
                "decision": "supplemented",
                "decided_by": "admin",
                "supplement_text": "try using port 3307 instead",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "supplemented"

    async def test_decide_already_decided(self, client, db_session):
        incident = await create_incident_in_db(
            db_session, status="investigating", thread_id="test-thread"
        )
        approval = await create_approval_in_db(db_session, incident.id)

        # First decision
        await client.post(
            f"/api/approvals/{approval.id}/decide",
            json={"decision": "approved", "decided_by": "admin"},
        )

        # Second decision should conflict
        resp = await client.post(
            f"/api/approvals/{approval.id}/decide",
            json={"decision": "rejected", "decided_by": "admin"},
        )
        assert resp.status_code == 409

    async def test_decide_stopped_incident(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="stopped")
        approval = await create_approval_in_db(db_session, incident.id)

        resp = await client.post(
            f"/api/approvals/{approval.id}/decide",
            json={"decision": "approved", "decided_by": "admin"},
        )
        assert resp.status_code == 400

    async def test_decide_invalid_decision(self, client, db_session):
        incident = await create_incident_in_db(db_session, status="investigating")
        approval = await create_approval_in_db(db_session, incident.id)

        resp = await client.post(
            f"/api/approvals/{approval.id}/decide",
            json={"decision": "maybe", "decided_by": "admin"},
        )
        assert resp.status_code == 422

    async def test_decide_not_found(self, client):
        resp = await client.post(
            f"/api/approvals/{uuid.uuid4()}/decide",
            json={"decision": "approved", "decided_by": "admin"},
        )
        assert resp.status_code == 404
