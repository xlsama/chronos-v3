"""Agent integration test fixtures.

These tests require:
- docker-compose.dev.yml running (PG + Redis)
- docker-compose.agent.yml running (mysql-target, mongo-target, postgres-target)
- DASHSCOPE_API_KEY environment variable set
"""

import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

# Skip all agent tests if no LLM API key
pytestmark = [
    pytest.mark.skipif(not DASHSCOPE_API_KEY, reason="DASHSCOPE_API_KEY not set"),
    pytest.mark.agent,
    pytest.mark.timeout(300),
]


@pytest_asyncio.fixture(scope="session")
async def agent_app():
    """Full FastAPI app with lifespan (migrations, checkpointer, AgentRunner)."""
    from asgi_lifespan import LifespanManager
    from src.main import app

    async with LifespanManager(app) as manager:
        yield app


@pytest_asyncio.fixture(scope="session")
async def agent_client(agent_app) -> AsyncClient:
    """HTTPX client connected to the full app."""
    transport = ASGITransport(app=agent_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def poll_incident_status(
    client: AsyncClient,
    incident_id: str,
    target_statuses: set[str],
    timeout: float = 120.0,
    interval: float = 2.0,
) -> dict:
    """Poll GET /api/incidents/{id} until status matches or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/api/incidents/{incident_id}")
        data = resp.json()
        if data["status"] in target_statuses:
            return data
        await asyncio.sleep(interval)
    raise TimeoutError(
        f"Incident {incident_id} did not reach {target_statuses} within {timeout}s. "
        f"Current status: {data['status']}"
    )


async def poll_for_event(
    client: AsyncClient,
    incident_id: str,
    event_type: str,
    timeout: float = 120.0,
    interval: float = 2.0,
) -> dict:
    """Poll GET /api/incidents/{id}/events until event_type appears."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/api/incidents/{incident_id}/events")
        events = resp.json()
        for evt in events:
            if evt["event_type"] == event_type:
                return evt
        await asyncio.sleep(interval)
    raise TimeoutError(f"Event '{event_type}' not found for incident {incident_id}")


async def poll_for_terminal_state(
    client: AsyncClient,
    incident_id: str,
    timeout: float = 180.0,
    interval: float = 3.0,
) -> dict:
    """Poll until agent finishes (resolved, stopped, error, or done event)."""
    terminal_statuses = {"resolved", "stopped", "error"}
    deadline = asyncio.get_event_loop().time() + timeout
    last_data = {}
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/api/incidents/{incident_id}")
        last_data = resp.json()
        if last_data["status"] in terminal_statuses:
            return last_data

        # Also check for ask_human, approval_required, confirm_resolution events
        # that need interaction
        events_resp = await client.get(f"/api/incidents/{incident_id}/events")
        events = events_resp.json()
        event_types = {e["event_type"] for e in events}

        if "confirm_resolution_required" in event_types:
            # Auto-confirm
            await client.post(f"/api/incidents/{incident_id}/confirm-resolution")
            await asyncio.sleep(interval)
            continue

        if "ask_human" in event_types and last_data["status"] == "investigating":
            # Auto-reply
            await client.post(
                f"/api/incidents/{incident_id}/messages",
                json={"content": "请继续自动排查，不需要额外信息。"},
            )
            await asyncio.sleep(interval)
            continue

        await asyncio.sleep(interval)

    raise TimeoutError(
        f"Incident {incident_id} did not reach terminal state within {timeout}s. "
        f"Last status: {last_data.get('status', 'unknown')}"
    )
