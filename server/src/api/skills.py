from fastapi import APIRouter

from src.api.schemas import (
    SkillCreate,
    SkillDetailResponse,
    SkillResponse,
    SkillUpdate,
)
from src.lib.errors import NotFoundError, AppError
from src.services.skill_service import SkillService

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _get_service() -> SkillService:
    return SkillService()


@router.get("", response_model=list[SkillResponse])
async def list_skills():
    service = _get_service()
    return [
        SkillResponse(
            slug=s.slug,
            name=s.name or "",
            description=s.description or "",
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in service.list_skills()
    ]


@router.get("/{slug}", response_model=SkillDetailResponse)
async def get_skill(slug: str):
    service = _get_service()
    try:
        meta, content = service.get_skill(slug)
    except FileNotFoundError:
        raise NotFoundError(f"Skill '{slug}' not found")
    return SkillDetailResponse(
        slug=meta.slug,
        name=meta.name or "",
        description=meta.description or "",
        content=content,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreate):
    service = _get_service()
    try:
        meta = service.create_skill(slug=body.slug)
    except FileExistsError:
        raise AppError(f"Skill '{body.slug}' already exists", status_code=409)
    return SkillResponse(
        slug=meta.slug,
        name=meta.name or "",
        description=meta.description or "",
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


@router.put("/{slug}", response_model=SkillResponse)
async def update_skill(slug: str, body: SkillUpdate):
    service = _get_service()
    try:
        meta = service.update_skill(slug=slug, content=body.content)
    except FileNotFoundError:
        raise NotFoundError(f"Skill '{slug}' not found")
    return SkillResponse(
        slug=meta.slug,
        name=meta.name or "",
        description=meta.description or "",
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


@router.delete("/{slug}")
async def delete_skill(slug: str):
    service = _get_service()
    try:
        service.delete_skill(slug)
    except FileNotFoundError:
        raise NotFoundError(f"Skill '{slug}' not found")
    return {"ok": True}
