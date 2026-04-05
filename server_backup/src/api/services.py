import asyncio
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    BatchCreateResult,
    BatchServiceCreate,
    InlineServiceTest,
    PaginatedResponse,
    ServiceCreate,
    ServiceResponse,
    ServiceUpdate,
    ServerTestResponse,
)
from src.env import get_settings
from src.db.connection import get_session
from src.db.models import Service
from src.lib.errors import NotFoundError
from src.lib.logger import get_logger
from src.services.crypto import CryptoService
from src.services.service_service import ServiceService

log = get_logger()

router = APIRouter(prefix="/api/services", tags=["services"])


def _get_service_service(session: AsyncSession) -> ServiceService:
    crypto = CryptoService(key=get_settings().encryption_key)
    return ServiceService(session=session, crypto=crypto)


@router.post("", response_model=ServiceResponse)
async def create_service(
    body: ServiceCreate,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.create(**body.model_dump())
    return _to_response(service)


@router.post("/batch", response_model=BatchCreateResult)
async def batch_create_services(
    body: BatchServiceCreate,
    session: AsyncSession = Depends(get_session),
):
    log.info("批量创建服务: 开始", total_items=len(body.items))
    svc = _get_service_service(session)
    created = 0
    skipped = 0
    errors: list[str] = []
    for i, item in enumerate(body.items):
        try:
            await svc.create(**item.model_dump())
            created += 1
            log.info(
                "批量创建服务: 成功",
                index=i,
                name=item.name,
                service_type=item.service_type,
                host=item.host,
                port=item.port,
            )
        except Exception as e:
            await session.rollback()
            msg = str(e).lower()
            if "already exists" in msg or "unique" in msg or "duplicate" in msg:
                skipped += 1
                log.warning("批量创建服务: 跳过(已存在)", index=i, name=item.name)
            else:
                errors.append(f"{item.name}: {e}")
                log.error("批量创建服务: 失败", index=i, name=item.name, error=str(e))
    log.info(
        "批量创建服务: 完成",
        created=created,
        skipped=skipped,
        errors=len(errors),
    )
    return BatchCreateResult(created=created, skipped=skipped, errors=errors)


@router.post("/test-inline", response_model=ServerTestResponse)
async def test_service_inline(body: InlineServiceTest):
    """Test a service connection without persisting — accepts raw params."""
    from src.ops_agent.tools.service_exec_tool import create_connector
    from src.services.service_service import _PROBE_COMMANDS, _friendly_error

    try:
        connector = create_connector(
            service_type=body.service_type,
            host=body.host,
            port=body.port,
            password=body.password,
            config=body.config,
        )
    except ValueError as e:
        return ServerTestResponse(success=False, message=str(e))

    probe = _PROBE_COMMANDS.get(body.service_type, "SELECT 1")
    try:
        result = await asyncio.wait_for(connector.execute(probe), timeout=10)
        if result.success:
            return ServerTestResponse(
                success=True,
                message=f"{body.service_type} 服务连接测试成功",
            )
        return ServerTestResponse(success=False, message=f"探测命令失败: {result.error}")
    except asyncio.TimeoutError:
        return ServerTestResponse(
            success=False,
            message=f"连接 {body.host}:{body.port} 超时（10秒）",
        )
    except Exception as e:
        return ServerTestResponse(success=False, message=_friendly_error(body.service_type, e))
    finally:
        try:
            await connector.close()
        except Exception:
            pass


@router.get("", response_model=PaginatedResponse[ServiceResponse])
async def list_services(
    page: int = 1,
    page_size: int = 50,
    type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(func.count()).select_from(Service)
    if type:
        stmt = stmt.where(Service.service_type == type)
    total = await session.scalar(stmt) or 0

    svc = _get_service_service(session)
    items = await svc.list_all(service_type=type)
    start = (page - 1) * page_size
    paged = items[start : start + page_size]
    return PaginatedResponse(
        items=[_to_response(s) for s in paged],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.get(service_id)
    if not service:
        raise NotFoundError("Service not found")
    return _to_response(service)


@router.patch("/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: uuid.UUID,
    body: ServiceUpdate,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.get(service_id)
    if not service:
        raise NotFoundError("Service not found")
    data = body.model_dump(exclude_unset=True)
    service = await svc.update(service, **data)
    return _to_response(service)


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.get(service_id)
    if not service:
        raise NotFoundError("Service not found")
    await svc.delete(service)
    return Response(status_code=204)


@router.post("/{service_id}/test", response_model=ServerTestResponse)
async def test_service(
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_service_service(session)
    service = await svc.get(service_id)
    if not service:
        raise NotFoundError("Service not found")
    success, message = await svc.test_connection(service)
    # Update status
    service.status = "online" if success else "offline"
    await session.commit()
    return ServerTestResponse(success=success, message=message)


def _to_response(service: Service) -> ServiceResponse:
    return ServiceResponse(
        id=service.id,
        name=service.name,
        description=service.description,
        service_type=service.service_type,
        host=service.host,
        port=service.port,
        config=service.config or {},
        has_password=service.encrypted_password is not None,
        status=service.status,
        created_at=service.created_at,
        updated_at=service.updated_at,
    )
