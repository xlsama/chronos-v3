"""Test data factories — return dicts suitable for API request bodies."""

import uuid


def make_server_payload(**overrides) -> dict:
    defaults = {
        "name": f"test-server-{uuid.uuid4().hex[:6]}",
        "host": "192.168.1.100",
        "port": 22,
        "username": "root",
        "password": "test-pass",
    }
    defaults.update(overrides)
    return defaults


def make_service_payload(**overrides) -> dict:
    defaults = {
        "name": f"test-service-{uuid.uuid4().hex[:6]}",
        "service_type": "mysql",
        "host": "192.168.1.200",
        "port": 3306,
        "password": "test-pass",
        "config": {},
    }
    defaults.update(overrides)
    return defaults


def make_project_payload(**overrides) -> dict:
    slug = uuid.uuid4().hex[:6]
    defaults = {
        "name": f"Test Project {slug}",
        "slug": f"test-project-{slug}",
    }
    defaults.update(overrides)
    return defaults


def make_incident_payload(**overrides) -> dict:
    defaults = {
        "description": f"Test incident {uuid.uuid4().hex[:6]}",
        "severity": "P3",
    }
    defaults.update(overrides)
    return defaults


def make_document_payload(**overrides) -> dict:
    defaults = {
        "filename": f"test-doc-{uuid.uuid4().hex[:6]}.md",
        "content": "# Test Document\n\nSome content.",
        "doc_type": "markdown",
    }
    defaults.update(overrides)
    return defaults


def make_approval_decision_payload(**overrides) -> dict:
    defaults = {
        "decision": "approved",
        "decided_by": "test-admin",
    }
    defaults.update(overrides)
    return defaults


def make_register_payload(**overrides) -> dict:
    hex = uuid.uuid4().hex[:6]
    defaults = {
        "email": f"test-{hex}@chronos.dev",
        "password": "Test1234!",
        "name": f"Test User {hex}",
    }
    defaults.update(overrides)
    return defaults


def make_notification_settings_payload(**overrides) -> dict:
    defaults = {
        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook",
        "enabled": True,
    }
    defaults.update(overrides)
    return defaults
