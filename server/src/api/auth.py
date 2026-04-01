"""Auth API — register, login, me, avatar, password."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from src.db.connection import get_session
from src.db.models import User
from src.env import get_settings
from src.lib.errors import NotFoundError, ValidationError
from src.lib.paths import uploads_dir
from src.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_service(session: AsyncSession) -> AuthService:
    return AuthService(session=session, jwt_secret=get_settings().jwt_secret)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    service = _auth_service(session)
    user = await service.register(email=body.email, password=body.password, name=body.name)
    return user


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    service = _auth_service(session)
    user = await service.authenticate(email=body.email, password=body.password)
    token = service.create_access_token(user_id=user.id, email=user.email)
    return AuthResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


@router.put("/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    fname = file.filename or "avatar"
    ext = Path(fname).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValidationError("仅支持 png/jpg/jpeg/webp 格式")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise ValidationError("头像文件不能超过 5MB")

    # 删除旧头像
    if user.avatar:
        old_path = uploads_dir() / user.avatar
        if old_path.exists():
            old_path.unlink()

    # 保存新文件
    stored_name = f"{uuid.uuid4()}{ext}"
    (uploads_dir() / stored_name).write_bytes(content)

    user.avatar = stored_name
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/avatar/{filename}")
async def get_avatar(filename: str):
    file_path = uploads_dir() / filename
    if not file_path.exists() or file_path.resolve().parent != uploads_dir().resolve():
        raise NotFoundError("头像不存在")
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    return FileResponse(
        path=str(file_path),
        media_type=media_types.get(file_path.suffix.lower(), "application/octet-stream"),
    )


@router.put("/password", response_model=UserResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = _auth_service(session)
    user = await service.change_password(user, body.old_password, body.new_password)
    return user
