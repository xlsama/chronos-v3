import uuid

from langchain_openai import ChatOpenAI
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.db.connection import get_session_factory
from src.db.models import Incident, Project
from src.lib.logger import logger
from src.ops_agent.state import OpsState
from src.services.crypto import CryptoService
from src.services.monitoring_source_service import MonitoringSourceService
from src.services.project_service import ProjectService


async def _check_monitoring_sources(project_id: str) -> tuple[bool, bool]:
    """Check if a project has Prometheus and/or Loki monitoring sources."""
    try:
        settings = get_settings()
        async with get_session_factory()() as session:
            crypto = CryptoService(key=settings.encryption_key)
            ms_service = MonitoringSourceService(session=session, crypto=crypto)
            return await ms_service.has_source_types(uuid.UUID(project_id))
    except Exception as e:
        logger.warning(f"Failed to check monitoring sources: {e}")
        return False, False


async def _match_project_with_llm(
    projects: list[Project], title: str, description: str
) -> str | None:
    """Use LLM to match the incident to a project. Returns project_id or None."""
    settings = get_settings()

    project_descriptions = []
    for p in projects:
        services_str = ""
        if p.services:
            service_names = [s.name for s in p.services]
            services_str = f", services: {', '.join(service_names)}"
        project_descriptions.append(
            f"- id: {p.id}, name: {p.name}, description: {p.description or 'N/A'}{services_str}"
        )

    prompt = f"""Based on the incident information, determine which project it belongs to.

## Available Projects
{chr(10).join(project_descriptions)}

## Incident
Title: {title}
Description: {description}

## Instructions
Analyze the incident and match it to the most relevant project based on project name, description, and services.
If you can confidently match, respond with ONLY the project ID (UUID format).
If you cannot determine the project, respond with ONLY the word "null".
Do not include any other text."""

    try:
        llm = ChatOpenAI(
            model=settings.mini_model,
            api_key=settings.dashscope_api_key,
            base_url=settings.llm_base_url,
            temperature=0,
        )
        response = await llm.ainvoke(prompt)
        result = response.content.strip().strip('"').strip("'")

        if result.lower() == "null":
            return None

        # Validate it's a real project ID
        valid_ids = {str(p.id) for p in projects}
        if result in valid_ids:
            return result

        logger.warning(f"LLM returned invalid project_id: {result}")
        return None
    except Exception as e:
        logger.error(f"LLM project matching failed: {e}")
        return None


async def discover_project_node(state: OpsState) -> dict:
    """Discover and set the project for an incident using LLM matching."""
    incident_id = state["incident_id"]
    project_id = state.get("project_id", "")
    title = state["title"]
    description = state["description"]

    # If project_id is already set (passed from API), just check monitoring sources
    if project_id:
        has_prometheus, has_loki = await _check_monitoring_sources(project_id)
        return {"has_prometheus": has_prometheus, "has_loki": has_loki}

    # Query all projects with their services for matching
    async with get_session_factory()() as session:
        service = ProjectService(session=session)
        # Use selectinload to eagerly load services
        from sqlalchemy import select

        result = await session.execute(
            select(Project)
            .options(selectinload(Project.services))
            .order_by(Project.created_at.desc())
        )
        projects = list(result.scalars().all())

    if not projects:
        logger.info(f"No projects found, skipping project discovery for incident {incident_id}")
        return {}

    # Single project → auto-select
    if len(projects) == 1:
        matched_id = str(projects[0].id)
        logger.info(f"Auto-selected sole project {projects[0].name} for incident {incident_id}")
    else:
        # Multiple projects → LLM matching
        matched_id = await _match_project_with_llm(projects, title, description)

    if not matched_id:
        logger.info(f"Could not match project for incident {incident_id}, continuing without project")
        return {}

    # Update incident in DB
    async with get_session_factory()() as session:
        incident = await session.get(Incident, uuid.UUID(incident_id))
        if incident:
            incident.project_id = uuid.UUID(matched_id)
            await session.commit()
            logger.info(f"Set project_id={matched_id} for incident {incident_id}")

    # Check monitoring sources
    has_prometheus, has_loki = await _check_monitoring_sources(matched_id)

    return {
        "project_id": matched_id,
        "has_prometheus": has_prometheus,
        "has_loki": has_loki,
    }
