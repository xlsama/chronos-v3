"""Agent integration test: basic incident lifecycle.

Tests the full flow:
1. Register a target MySQL service
2. Create a project
3. Create an incident
4. Agent starts investigating
5. Poll for completion (auto-approve, auto-reply to questions)
6. Verify final state
"""

import pytest

from tests.agent.conftest import poll_for_terminal_state, poll_incident_status
from tests.factories import make_project_payload, make_service_payload

pytestmark = [pytest.mark.agent, pytest.mark.timeout(300)]


async def test_simple_incident_lifecycle(agent_client):
    """Verify the full incident lifecycle: create -> investigating -> terminal state."""
    client = agent_client

    # 1. Register a MySQL service pointing to the test target
    svc_resp = await client.post(
        "/api/services",
        json=make_service_payload(
            name="test-mysql-target",
            service_type="mysql",
            host="localhost",
            port=13306,
            password="testpass",
            config={"database": "testdb", "username": "testuser"},
        ),
    )
    assert svc_resp.status_code == 200, f"Failed to create service: {svc_resp.text}"

    # 2. Create a project
    proj_resp = await client.post("/api/projects", json=make_project_payload())
    assert proj_resp.status_code == 200

    # 3. Create an incident
    incident_resp = await client.post(
        "/api/incidents",
        json={
            "description": (
                "MySQL testdb 库 orders 表查询超时，SELECT COUNT(*) 执行超过 30 秒，"
                "请排查原因。数据库服务名: test-mysql-target"
            ),
            "severity": "P2",
        },
    )
    assert incident_resp.status_code == 200
    incident_id = incident_resp.json()["id"]
    assert incident_resp.json()["status"] == "open"

    # 4. Wait for agent to start investigating
    await poll_incident_status(
        client, incident_id, {"investigating"}, timeout=30
    )

    # 5. Wait for terminal state (auto-handle interrupts)
    final = await poll_for_terminal_state(client, incident_id, timeout=180)

    # 6. Verify final state
    assert final["status"] in ("resolved", "stopped", "error"), (
        f"Unexpected final status: {final['status']}"
    )

    # Verify messages were generated
    msgs_resp = await client.get(f"/api/incidents/{incident_id}/messages")
    assert msgs_resp.status_code == 200
    messages = msgs_resp.json()
    assert len(messages) > 0, "Agent should have generated at least one message"

    # Verify thread_id was set
    incident_detail = await client.get(f"/api/incidents/{incident_id}")
    assert incident_detail.json()["thread_id"] is not None
