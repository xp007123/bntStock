"""注册、登录、退出、当前用户。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ...auth.deps import COOKIE, auth_service, current_user
from ...auth.service import SESSION_DAYS, AuthError, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    username: str
    phone: str
    password: str
    confirm: str


class LoginBody(BaseModel):
    account: str
    password: str


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "")


@router.post("/register")
def register(body: RegisterBody, request: Request):
    try:
        auth_service(request).register(body.username, body.phone, body.password, body.confirm, ip=_client_ip(request))
    except AuthError as exc:
        raise HTTPException(429 if exc.code == "locked" else 422, {"message": str(exc), "field": exc.code}) from exc
    return {"status": "pending", "message": "注册已提交，管理员审核通过后即可登录"}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    try:
        user, token = auth_service(request).authenticate(body.account, body.password, _client_ip(request))
    except AuthError as exc:
        status = 429 if exc.code == "locked" else 403 if exc.code in ("pending", "rejected", "disabled") else 401
        raise HTTPException(status, {"message": str(exc), "field": exc.code}) from exc
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=os.environ.get("SIXIANG_COOKIE_SECURE") == "1", path="/")
    return user.public()


@router.post("/logout")
def logout(request: Request, response: Response):
    auth_service(request).logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user.public()
