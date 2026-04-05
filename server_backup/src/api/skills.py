from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    SkillCreate,
    SkillDetailResponse,
    SkillFileUpdate,
    SkillResponse,
    SkillUpdate,
)
from src.db.connection import get_session
from src.lib.errors import NotFoundError, AppError
from src.services.skill_service import SkillService
from src.services.version_service import VersionService

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _get_service() -> SkillService:
    return SkillService()


def _to_response(meta) -> SkillResponse:
    return SkillResponse(
        slug=meta.slug,
        name=meta.name or "",
        description=meta.description or "",
        has_scripts=meta.has_scripts,
        has_references=meta.has_references,
        has_assets=meta.has_assets,
        draft=meta.draft,
        when_to_use=meta.when_to_use,
        tags=meta.tags,
        related_services=meta.related_services,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


@router.get("", response_model=list[SkillResponse])
async def list_skills():
    service = _get_service()
    return [_to_response(s) for s in service.list_skills()]


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
        has_scripts=meta.has_scripts,
        has_references=meta.has_references,
        has_assets=meta.has_assets,
        draft=meta.draft,
        script_files=meta.script_files,
        reference_files=meta.reference_files,
        asset_files=meta.asset_files,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreate, session: AsyncSession = Depends(get_session)):
    service = _get_service()
    try:
        meta = service.create_skill(slug=body.slug)
    except FileExistsError:
        raise AppError(f"Skill '{body.slug}' already exists", status_code=409)

    # 保存初始版本
    _, content = service.get_skill(body.slug)
    vs = VersionService(session)
    await vs.save_version(
        entity_type="skill", entity_id=body.slug, content=content, change_source="init"
    )
    await session.commit()

    return _to_response(meta)


@router.put("/{slug}", response_model=SkillResponse)
async def update_skill(slug: str, body: SkillUpdate, session: AsyncSession = Depends(get_session)):
    service = _get_service()
    try:
        meta = service.update_skill(slug=slug, content=body.content)
    except FileNotFoundError:
        raise NotFoundError(f"Skill '{slug}' not found")

    # 保存新内容为版本（去重会自动处理内容未变的情况）
    vs = VersionService(session)
    await vs.save_version(
        entity_type="skill", entity_id=slug, content=body.content, change_source="manual"
    )
    await session.commit()

    return _to_response(meta)


@router.delete("/{slug}")
async def delete_skill(slug: str, session: AsyncSession = Depends(get_session)):
    service = _get_service()
    try:
        service.delete_skill(slug)
    except FileNotFoundError:
        raise NotFoundError(f"Skill '{slug}' not found")
    # 清理版本历史
    vs = VersionService(session)
    await vs.delete_versions("skill", slug)
    await session.commit()
    return {"ok": True}


# ── File Management ──────────────────────────────────────────


@router.get("/{slug}/files/{path:path}")
async def get_skill_file(slug: str, path: str):
    service = _get_service()
    try:
        content = service.read_skill_file(slug, path)
    except FileNotFoundError:
        raise NotFoundError(f"File '{path}' not found in skill '{slug}'")
    except ValueError as e:
        raise AppError(str(e), status_code=400)
    return {"content": content}


@router.put("/{slug}/files/{path:path}")
async def put_skill_file(slug: str, path: str, body: SkillFileUpdate):
    service = _get_service()
    try:
        service.write_skill_file(slug, path, body.content)
    except FileNotFoundError:
        raise NotFoundError(f"Skill '{slug}' not found")
    except ValueError as e:
        raise AppError(str(e), status_code=400)
    return {"ok": True}


@router.delete("/{slug}/files/{path:path}")
async def delete_skill_file(slug: str, path: str):
    service = _get_service()
    try:
        service.delete_skill_file(slug, path)
    except FileNotFoundError:
        raise NotFoundError(f"File '{path}' not found in skill '{slug}'")
    except ValueError as e:
        raise AppError(str(e), status_code=400)
    return {"ok": True}
