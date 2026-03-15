"""Tests for database models — field existence and FK relationships."""

import uuid
from datetime import datetime

from src.db.models import (
    ApprovalRequest,
    DocumentChunk,
    Incident,
    Infrastructure,
    Message,
    Project,
    ProjectDocument,
)


class TestProjectModel:
    def test_has_required_fields(self):
        project = Project(
            name="My Project",
            slug="my-project",
            description="desc",
            cloud_md="# Cloud",
        )
        assert project.name == "My Project"
        assert project.slug == "my-project"
        assert project.description == "desc"
        assert project.cloud_md == "# Cloud"

    def test_id_column_has_default(self):
        col = Project.__table__.c.id
        assert col.default is not None

    def test_tablename(self):
        assert Project.__tablename__ == "projects"


class TestProjectDocumentModel:
    def test_has_required_fields(self):
        pid = uuid.uuid4()
        doc = ProjectDocument(
            project_id=pid,
            filename="readme.md",
            content="# Hello",
            doc_type="markdown",
            status="ready",
        )
        assert doc.project_id == pid
        assert doc.filename == "readme.md"
        assert doc.content == "# Hello"
        assert doc.doc_type == "markdown"
        assert doc.status == "ready"

    def test_tablename(self):
        assert ProjectDocument.__tablename__ == "project_documents"


class TestDocumentChunkModel:
    def test_has_required_fields(self):
        doc_id = uuid.uuid4()
        pid = uuid.uuid4()
        chunk = DocumentChunk(
            document_id=doc_id,
            project_id=pid,
            chunk_index=0,
            content="chunk text",
        )
        assert chunk.document_id == doc_id
        assert chunk.project_id == pid
        assert chunk.chunk_index == 0
        assert chunk.content == "chunk text"

    def test_tablename(self):
        assert DocumentChunk.__tablename__ == "document_chunks"


class TestInfrastructureForeignKey:
    def test_has_project_id_column(self):
        infra = Infrastructure(
            name="srv",
            host="1.2.3.4",
            project_id=uuid.uuid4(),
        )
        assert infra.project_id is not None

    def test_project_id_fk_defined(self):
        col = Infrastructure.__table__.c.project_id
        fks = [fk.target_fullname for fk in col.foreign_keys]
        assert "projects.id" in fks


class TestIncidentForeignKey:
    def test_has_project_id_column(self):
        inc = Incident(
            title="t",
            description="d",
            project_id=uuid.uuid4(),
        )
        assert inc.project_id is not None

    def test_project_id_fk_defined(self):
        col = Incident.__table__.c.project_id
        fks = [fk.target_fullname for fk in col.foreign_keys]
        assert "projects.id" in fks


class TestRelationships:
    def test_project_has_documents_relationship(self):
        assert "documents" in Project.__mapper__.relationships

    def test_project_has_infrastructures_relationship(self):
        assert "infrastructures" in Project.__mapper__.relationships

    def test_project_has_incidents_relationship(self):
        assert "incidents" in Project.__mapper__.relationships

    def test_project_document_has_chunks_relationship(self):
        assert "chunks" in ProjectDocument.__mapper__.relationships

    def test_project_document_has_project_relationship(self):
        assert "project" in ProjectDocument.__mapper__.relationships
