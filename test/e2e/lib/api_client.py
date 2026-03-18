from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "http://localhost:8000"


class ApiClient:
    def __init__(self, base_url: str = BASE_URL) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=30)

    def create_project(self, name: str, description: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        resp = self._client.post("/api/projects", json=body)
        resp.raise_for_status()
        return resp.json()

    def create_server(
        self,
        name: str,
        host: str,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "host": host, "port": port, "username": username}
        if password is not None:
            body["password"] = password
        if description is not None:
            body["description"] = description
        resp = self._client.post("/api/servers", json=body)
        resp.raise_for_status()
        return resp.json()

    def update_project(self, project_id: str, linked_server_ids: list[str] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if linked_server_ids is not None:
            body["linked_server_ids"] = linked_server_ids
        resp = self._client.patch(f"/api/projects/{project_id}", json=body)
        resp.raise_for_status()
        return resp.json()

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/api/incidents/{incident_id}")
        resp.raise_for_status()
        return resp.json()

    def decide_approval(self, approval_id: str, decision: str = "approved") -> None:
        resp = self._client.post(
            f"/api/approvals/{approval_id}/decide",
            json={"decision": decision, "decided_by": "e2e-test"},
        )
        resp.raise_for_status()
