"""Tests for /api/attachments endpoints."""

import uuid

from tests.api.conftest import create_incident_in_db


class TestUploadFiles:
    async def test_upload_single_file(self, client):
        resp = await client.post(
            "/api/attachments",
            files={"files": ("test.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test.txt"
        assert data[0]["content_type"] == "text/plain"
        assert data[0]["size"] == 11
        assert data[0]["incident_id"] is None

    async def test_upload_multiple_files(self, client):
        resp = await client.post(
            "/api/attachments",
            files=[
                ("files", ("a.txt", b"aaa", "text/plain")),
                ("files", ("b.txt", b"bbb", "text/plain")),
            ],
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_upload_with_incident_id(self, client, db_session):
        incident = await create_incident_in_db(db_session)

        resp = await client.post(
            "/api/attachments",
            params={"incident_id": str(incident.id)},
            files={"files": ("test.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.json()[0]["incident_id"] == str(incident.id)

    async def test_upload_text_file_parsed(self, client):
        resp = await client.post(
            "/api/attachments",
            files={"files": ("readme.txt", b"This is the content.", "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()[0]
        assert data["parsed_content"] is not None
        assert "content" in data["parsed_content"].lower() or len(data["parsed_content"]) > 0


class TestDownloadFile:
    async def test_download_file(self, client):
        upload_resp = await client.post(
            "/api/attachments",
            files={"files": ("test.txt", b"hello world", "text/plain")},
        )
        attachment_id = upload_resp.json()[0]["id"]

        resp = await client.get(f"/api/attachments/{attachment_id}/download")
        assert resp.status_code == 200
        assert resp.content == b"hello world"

    async def test_download_not_found(self, client):
        resp = await client.get(f"/api/attachments/{uuid.uuid4()}/download")
        assert resp.status_code == 404
