"""Auth API tests — register, login, me."""

import jwt
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from tests.factories import make_register_payload

pytestmark = pytest.mark.asyncio


async def _register_and_login(client: AsyncClient, payload: dict | None = None) -> dict:
    """Helper: register a user, login, return {"headers": ..., "user_payload": ...}."""
    payload = payload or make_register_payload()
    await client.post("/api/auth/register", json=payload)
    resp = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    token = resp.json()["access_token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "user_payload": payload,
    }


# ── Register ─────────────────────────────────────────────────────────


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        payload = make_register_payload()
        resp = await client.post("/api/auth/register", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == payload["email"]
        assert data["name"] == payload["name"]
        assert data["is_active"] is True
        assert "id" in data
        assert "hashed_password" not in data

    async def test_register_duplicate_email(self, client: AsyncClient):
        payload = make_register_payload()
        resp1 = await client.post("/api/auth/register", json=payload)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/auth/register", json=payload)
        assert resp2.status_code == 409

    async def test_register_weak_password(self, client: AsyncClient):
        payload = make_register_payload(password="12345")
        resp = await client.post("/api/auth/register", json=payload)
        assert resp.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        payload = make_register_payload(email="not-an-email")
        resp = await client.post("/api/auth/register", json=payload)
        assert resp.status_code == 422


# ── Login ────────────────────────────────────────────────────────────


class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        payload = make_register_payload()
        await client.post("/api/auth/register", json=payload)
        resp = await client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        payload = make_register_payload()
        await client.post("/api/auth/register", json=payload)
        resp = await client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": "WrongPass1!"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_email(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/login",
            json={"email": "nobody@chronos.dev", "password": "Whatever1!"},
        )
        assert resp.status_code == 401


# ── Me ───────────────────────────────────────────────────────────────


class TestMe:
    async def test_me_authenticated(self, client: AsyncClient):
        auth = await _register_and_login(client)
        resp = await client.get("/api/auth/me", headers=auth["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == auth["user_payload"]["email"]
        assert data["name"] == auth["user_payload"]["name"]

    async def test_me_no_token(self, client: AsyncClient):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    async def test_me_invalid_token(self, client: AsyncClient):
        resp = await client.get(
            "/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert resp.status_code == 401

    async def test_me_expired_token(self, client: AsyncClient):
        from src.env import get_settings

        expired_payload = {
            "sub": "00000000-0000-0000-0000-000000000000",
            "email": "expired@test.dev",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(expired_payload, get_settings().jwt_secret, algorithm="HS256")
        resp = await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401
