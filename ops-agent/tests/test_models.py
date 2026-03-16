"""Tests for database models — field existence and FK relationships."""

import uuid
from datetime import datetime

from src.db.models import (
    ApprovalRequest,
    DocumentChunk,
    Incident,
    Infrastructure,
    Message,
    MonitoringSource,
    Project,
    ProjectDocument,
    Service,
    ServiceDependency,
)


class TestProjectModel:
    def test_has_required_fields(self):
        project = Project(
            name="My Project",
            slug="my-project",
            description="desc",
            service_md="# Cloud",
        )
        assert project.name == "My Project"
        assert project.slug == "my-project"
        assert project.description == "desc"
        assert project.service_md == "# Cloud"

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

    def test_has_chunk_metadata_field(self):
        chunk = DocumentChunk(
            document_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            chunk_index=0,
            content="text",
            chunk_metadata={"page": 3},
        )
        assert chunk.chunk_metadata == {"page": 3}

    def test_chunk_metadata_defaults_to_dict(self):
        col = DocumentChunk.__table__.c.metadata
        assert col.server_default is not None

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


# ── Infrastructure extended fields ──


class TestInfrastructureModel:
    def test_has_type_field(self):
        infra = Infrastructure(name="test", type="kubernetes")
        assert infra.type == "kubernetes"

    def test_has_conn_config_field(self):
        infra = Infrastructure(name="test", conn_config="encrypted-data")
        assert infra.conn_config == "encrypted-data"

    def test_has_services_relationship(self):
        assert "services" in Infrastructure.__mapper__.relationships

    def test_type_default(self):
        col = Infrastructure.__table__.c.type
        assert col.default is not None


# ── Service model ──


class TestServiceModel:
    def test_has_required_fields(self):
        infra_id = uuid.uuid4()
        svc = Service(
            infrastructure_id=infra_id,
            name="nginx",
            service_type="nginx",
            port=80,
            namespace="default",
        )
        assert svc.name == "nginx"
        assert svc.service_type == "nginx"
        assert svc.port == 80
        assert svc.namespace == "default"
        assert svc.infrastructure_id == infra_id

    def test_tablename(self):
        assert Service.__tablename__ == "services"

    def test_infrastructure_id_fk(self):
        col = Service.__table__.c.infrastructure_id
        fks = [fk.target_fullname for fk in col.foreign_keys]
        assert "infrastructures.id" in fks

    def test_has_infrastructure_relationship(self):
        assert "infrastructure" in Service.__mapper__.relationships

    def test_has_depends_on_relationship(self):
        assert "depends_on" in Service.__mapper__.relationships


# ── ServiceDependency model ──


class TestServiceDependencyModel:
    def test_has_required_fields(self):
        svc_id = uuid.uuid4()
        dep_id = uuid.uuid4()
        dep = ServiceDependency(service_id=svc_id, depends_on_id=dep_id)
        assert dep.service_id == svc_id
        assert dep.depends_on_id == dep_id

    def test_tablename(self):
        assert ServiceDependency.__tablename__ == "service_dependencies"

    def test_service_id_fk(self):
        col = ServiceDependency.__table__.c.service_id
        fks = [fk.target_fullname for fk in col.foreign_keys]
        assert "services.id" in fks

    def test_depends_on_id_fk(self):
        col = ServiceDependency.__table__.c.depends_on_id
        fks = [fk.target_fullname for fk in col.foreign_keys]
        assert "services.id" in fks


# ── MonitoringSource model ──


class TestMonitoringSourceModel:
    def test_has_required_fields(self):
        pid = uuid.uuid4()
        src = MonitoringSource(
            project_id=pid,
            name="Prod Prometheus",
            source_type="prometheus",
            endpoint="http://prometheus:9090",
        )
        assert src.project_id == pid
        assert src.name == "Prod Prometheus"
        assert src.source_type == "prometheus"
        assert src.endpoint == "http://prometheus:9090"

    def test_tablename(self):
        assert MonitoringSource.__tablename__ == "monitoring_sources"

    def test_project_id_fk(self):
        col = MonitoringSource.__table__.c.project_id
        fks = [fk.target_fullname for fk in col.foreign_keys]
        assert "projects.id" in fks
