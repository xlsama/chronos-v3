from __future__ import annotations

import pytest

from ..lib.api_client import ApiClient
from ..lib.docker import TestInfra
from ..lib.fault_injector import FaultInjector
from ..lib.processes import ProcessManager
from ..lib.wait import wait_for_healthy


@pytest.fixture(scope="session")
def infra():
    infra = TestInfra("case-2")
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
    print("[seed] Seeding case-2 data...")

    project = api_client.create_project(
        name="微服务订单系统",
        description="订单系统依赖库存服务的微服务架构，用于 E2E 链路故障测试",
    )

    app_server = api_client.create_server(
        name="app-server",
        host="localhost",
        port=12223,
        username="root",
        password="testpassword",
    )

    data_server = api_client.create_server(
        name="data-server",
        host="localhost",
        port=12224,
        username="root",
        password="testpassword",
    )

    api_client.update_project(
        project["id"],
        linked_server_ids=[app_server["id"], data_server["id"]],
    )

    print("[seed] Seeding case-2 complete")
    return {"project": project, "app_server": app_server, "data_server": data_server}


@pytest.fixture
def app_injector() -> FaultInjector:
    return FaultInjector(port=12223)


@pytest.fixture
def data_injector() -> FaultInjector:
    return FaultInjector(port=12224)
