"""FastAPI 依赖：从会话 Cookie 识别当前用户。"""
from __future__ import annotations

from fastapi import HTTPException, Request

from .service import AuthService, User

COOKIE = "sx_session"


def auth_service(request: Request) -> AuthService:
    return request.app.state.auth


def current_user(request: Request) -> User:
    user = auth_service(request).user_for_token(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "请先登录")
    return user


def require_admin(request: Request) -> User:
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return user
