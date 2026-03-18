from __future__ import annotations

import pytest
from playwright.sync_api import Browser, BrowserContext, Page

from .lib.api_client import ApiClient
from .lib.docker import TestInfra
from .lib.processes import ProcessManager
from .lib.wait import wait_for_healthy


@pytest.fixture(scope="session")
def api_client() -> ApiClient:
    return ApiClient()


@pytest.fixture(scope="session")
def _infra_and_processes(request: pytest.FixtureRequest):
    case_name = getattr(request, "param", None)
    if case_name is None:
        yield
        return

    infra = TestInfra(case_name)
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


@pytest.fixture
def page(browser: Browser) -> Page:
    context = browser.new_context(base_url="http://localhost:5173")
    p = context.new_page()
    p.set_default_timeout(60_000)
    yield p
    context.close()
