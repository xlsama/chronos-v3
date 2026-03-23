from functools import lru_cache
from pathlib import Path

from src.env import get_settings


@lru_cache
def get_data_dir() -> Path:
    return Path(get_settings().data_dir)


@lru_cache
def get_seeds_dir() -> Path:
    return Path(get_settings().seeds_dir)


def skills_dir() -> Path:
    return get_data_dir() / "skills"


def incident_history_dir() -> Path:
    return get_data_dir() / "incident_history"


def knowledge_dir(project_slug: str | None = None) -> Path:
    base = get_data_dir() / "knowledge"
    return base / project_slug if project_slug else base


def seeds_skills_dir() -> Path:
    return get_seeds_dir() / "skills"
