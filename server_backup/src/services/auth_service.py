"""Authentication service — register, login, JWT token management."""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.lib.errors import AuthenticationError, ConflictError


class AuthService:
    def __init__(self, session: AsyncSession, jwt_secret: str):
        self.session = session
        self.jwt_secret = jwt_secret

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())

    def create_access_token(self, user_id: uuid.UUID, email: str) -> str:
        payload = {
            "sub": str(user_id),
            "email": email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    async def register(self, email: str, password: str, name: str) -> User:
        existing = (
            await self.session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("该邮箱已注册")

        user = User(
            email=email,
            hashed_password=self.hash_password(password),
            name=name,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def change_password(self, user: User, old_password: str, new_password: str) -> User:
        if not self.verify_password(old_password, user.hashed_password):
            raise AuthenticationError("旧密码不正确")
        user.hashed_password = self.hash_password(new_password)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = (
            await self.session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if not user:
            raise AuthenticationError("该邮箱未注册")
        if not self.verify_password(password, user.hashed_password):
            raise AuthenticationError("密码错误")
        if not user.is_active:
            raise AuthenticationError("账号已停用")
        return user
