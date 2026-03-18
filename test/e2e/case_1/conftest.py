from __future__ import annotations

import pytest

from ..lib.api_client import ApiClient
from ..lib.docker import TestInfra
from ..lib.fault_injector import FaultInjector
from ..lib.processes import ProcessManager
from ..lib.wait import wait_for_healthy


@pytest.fixture(scope="session")
def infra():
    infra = TestInfra("case-1")
    proc = ProcessManager()

    infra.start()
    proc.run_migrations()
    proc.start_server()
    wait_for_healthy("http://localhost:8000/api/projects", timeout=30)
    proc.start_frontend()
    wait_for_healthy("http://localhost:5173", timeout=30)

    yield

    proc.stop_all()
    infra.stop()


@pytest.fixture(scope="session")
def seed_data(api_client: ApiClient, infra):
    print("[seed] Seeding case-1 data...")

    project = api_client.create_project(
        name="E2E Test Project",
        description="Auto-created for E2E testing",
    )

    server = api_client.create_server(
        name="test-target",
        host="localhost",
        port=12222,
        username="root",
        password="testpassword",
    )

    api_client.update_project(project["id"], linked_server_ids=[server["id"]])

    print("[seed] Seeding complete")
    return {"project": project, "server": server}


@pytest.fixture
def fault_injector() -> FaultInjector:
    return FaultInjector()
