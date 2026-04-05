"""Shared FastAPI dependencies."""

import uuid

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_session
from src.db.models import User
from src.env import get_settings
from src.lib.errors import AuthenticationError


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing authorization token")

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    user = await session.get(User, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise AuthenticationError("User not found or deactivated")
    return user
