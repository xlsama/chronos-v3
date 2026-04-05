"""Tests for /api/projects/{pid}/documents and /api/documents endpoints."""

import uuid

from tests.factories import make_document_payload, make_project_payload


async def _create_project(client) -> str:
    """Helper to create a project and return its ID."""
    resp = await client.post("/api/projects", json=make_project_payload())
    return resp.json()["id"]


class TestUploadDocument:
    async def test_upload_document_json(self, client):
        project_id = await _create_project(client)
        payload = make_document_payload()

        resp = await client.post(
            f"/api/projects/{project_id}/documents", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == payload["filename"]
        assert data["doc_type"] == "markdown"
        assert data["project_id"] == project_id

    async def test_upload_document_empty_content(self, client):
        project_id = await _create_project(client)
        payload = make_document_payload(content="")

        resp = await client.post(
            f"/api/projects/{project_id}/documents", json=payload
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "indexed"

    async def test_upload_document_project_not_found(self, client):
        payload = make_document_payload()
        resp = await client.post(
            f"/api/projects/{uuid.uuid4()}/documents", json=payload
        )
        assert resp.status_code == 404


class TestUploadDocumentFile:
    async def test_upload_text_file(self, client):
        project_id = await _create_project(client)

        resp = await client.post(
            f"/api/projects/{project_id}/documents/upload",
            files={"file": ("readme.txt", b"# Hello\n\nWorld", "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "readme.txt"
        assert data["doc_type"] == "text"

    async def test_upload_markdown_file(self, client):
        project_id = await _create_project(client)

        resp = await client.post(
            f"/api/projects/{project_id}/documents/upload",
            files={"file": ("doc.md", b"# Title\n\nContent", "text/markdown")},
        )
        assert resp.status_code == 200
        assert resp.json()["doc_type"] == "markdown"


class TestListDocuments:
    async def test_list_documents_empty(self, client):
        project_id = await _create_project(client)

        resp = await client.get(f"/api/projects/{project_id}/documents")
        assert resp.status_code == 200
        # May contain auto-created MEMORY.md
        assert isinstance(resp.json(), list)

    async def test_list_documents(self, client):
        project_id = await _create_project(client)
        await client.post(
            f"/api/projects/{project_id}/documents",
            json=make_document_payload(),
        )

        resp = await client.get(f"/api/projects/{project_id}/documents")
        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) >= 1


class TestGetDocument:
    async def test_get_document(self, client):
        project_id = await _create_project(client)
        create_resp = await client.post(
            f"/api/projects/{project_id}/documents",
            json=make_document_payload(),
        )
        doc_id = create_resp.json()["id"]

        resp = await client.get(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert data["id"] == doc_id

    async def test_get_document_not_found(self, client):
        resp = await client.get(f"/api/documents/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateDocument:
    async def test_update_document(self, client):
        project_id = await _create_project(client)
        create_resp = await client.post(
            f"/api/projects/{project_id}/documents",
            json=make_document_payload(),
        )
        doc_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/documents/{doc_id}",
            json={"content": "# Updated\n\nNew content."},
        )
        assert resp.status_code == 200
        assert "Updated" in resp.json()["content"]

    async def test_update_document_not_found(self, client):
        resp = await client.put(
            f"/api/documents/{uuid.uuid4()}",
            json={"content": "x"},
        )
        assert resp.status_code == 404


class TestDeleteDocument:
    async def test_delete_document(self, client):
        project_id = await _create_project(client)
        create_resp = await client.post(
            f"/api/projects/{project_id}/documents",
            json=make_document_payload(),
        )
        doc_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        get_resp = await client.get(f"/api/documents/{doc_id}")
        assert get_resp.status_code == 404

    async def test_delete_memory_config_blocked(self, client):
        project_id = await _create_project(client)
        # Project auto-creates MEMORY.md, find it
        docs_resp = await client.get(f"/api/projects/{project_id}/documents")
        memory_doc = None
        for doc in docs_resp.json():
            if doc["doc_type"] == "memory_config":
                memory_doc = doc
                break

        if memory_doc:
            resp = await client.delete(f"/api/documents/{memory_doc['id']}")
            assert resp.status_code == 400

    async def test_delete_document_not_found(self, client):
        resp = await client.delete(f"/api/documents/{uuid.uuid4()}")
        assert resp.status_code == 404
