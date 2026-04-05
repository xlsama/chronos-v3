"""Tests for /api/notification-settings endpoints."""

from unittest.mock import AsyncMock, patch

from tests.factories import make_notification_settings_payload


class TestGetNotificationSettings:
    async def test_get_not_configured(self, client):
        resp = await client.get("/api/notification-settings/feishu")
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_get_after_upsert(self, client):
        payload = make_notification_settings_payload()
        await client.put("/api/notification-settings/feishu", json=payload)

        resp = await client.get("/api/notification-settings/feishu")
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "feishu"
        assert data["webhook_url"] == payload["webhook_url"]
        assert data["enabled"] is True


class TestUpsertNotificationSettings:
    async def test_upsert_create(self, client):
        payload = make_notification_settings_payload()
        resp = await client.put("/api/notification-settings/feishu", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "feishu"
        assert data["webhook_url"] == payload["webhook_url"]
        assert data["enabled"] is True
        assert "id" in data

    async def test_upsert_update(self, client):
        payload = make_notification_settings_payload()
        resp1 = await client.put("/api/notification-settings/feishu", json=payload)
        original_id = resp1.json()["id"]

        new_payload = make_notification_settings_payload(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/new-hook"
        )
        resp2 = await client.put("/api/notification-settings/feishu", json=new_payload)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == original_id
        assert resp2.json()["webhook_url"] == new_payload["webhook_url"]

    async def test_upsert_with_sign_key(self, client):
        payload = make_notification_settings_payload(sign_key="test-sign-key")
        resp = await client.put("/api/notification-settings/feishu", json=payload)
        assert resp.status_code == 200
        assert resp.json()["sign_key"] == "test-sign-key"

    async def test_upsert_disabled(self, client):
        payload = make_notification_settings_payload(enabled=False)
        resp = await client.put("/api/notification-settings/feishu", json=payload)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


class TestTestWebhook:
    @patch("src.api.notification_settings.send_feishu_message", new_callable=AsyncMock)
    async def test_webhook_success(self, mock_send, client):
        mock_send.return_value = None

        resp = await client.post(
            "/api/notification-settings/test/webhook",
            json={
                "webhook_url": "https://open.feishu.cn/hook/test",
                "platform": "feishu",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_send.assert_called_once()

    @patch("src.api.notification_settings.send_feishu_message", new_callable=AsyncMock)
    async def test_webhook_failure(self, mock_send, client):
        mock_send.side_effect = Exception("Connection refused")

        resp = await client.post(
            "/api/notification-settings/test/webhook",
            json={
                "webhook_url": "https://bad-url.example.com",
                "platform": "feishu",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Connection refused" in data["message"]
