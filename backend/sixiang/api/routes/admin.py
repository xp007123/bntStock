"""管理端：用户审核与数据同步状态。仅管理员可用。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ...auth.deps import auth_service, require_admin
from ...auth.service import AuthError, User

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class StatusBody(BaseModel):
    status: Literal["active", "rejected", "disabled"]
    note: str | None = None


class PasswordBody(BaseModel):
    password: str


@router.get("/users")
def list_users(request: Request, status: Literal["pending", "active", "rejected", "disabled"] | None = None):
    svc = auth_service(request)
    return {"counts": svc.counts(), "items": svc.list_users(status)}


@router.post("/users/{uid}/status")
def set_status(uid: int, body: StatusBody, request: Request, admin: User = Depends(require_admin)):
    try:
        return auth_service(request).set_status(uid, body.status, admin, body.note).public()
    except KeyError as exc:
        raise HTTPException(404, "用户不存在") from exc
    except AuthError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/users/{uid}/password")
def reset_password(uid: int, body: PasswordBody, request: Request):
    try:
        auth_service(request).reset_password(uid, body.password)
    except KeyError as exc:
        raise HTTPException(404, "用户不存在") from exc
    except AuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.get("/data/sync-status")
def sync_status(request: Request):
    from ...data.scheduler import read_status
    return read_status(request.app.state.settings.market_dir)


@router.post("/data/sync")
def run_sync(request: Request):
    """手动触发一次行情同步（后台运行，结果见同步状态）。"""
    import threading

    from ...data.scheduler import run_once
    threading.Thread(target=run_once, args=(request.app.state.settings.market_dir,), daemon=True).start()
    return {"state": "started"}
