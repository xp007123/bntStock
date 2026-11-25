"""我的判断：封存、列表、揭晓。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...auth.deps import current_user
from ...auth.service import User
from .ask import build_answer

router = APIRouter(prefix="/api/judgments", tags=["judgments"])


class SealBody(BaseModel):
    kind: Literal["stock", "option"]
    code: str
    horizon: int = Field(ge=1, le=250)
    fee: float | None = Field(default=None, gt=0, lt=1)


@router.post("")
def seal(body: SealBody, request: Request, user: User = Depends(current_user)):
    """服务端按当前数据重新计算后封存，不接受客户端传来的数字。"""
    if body.kind == "option" and body.fee is None:
        raise HTTPException(422, "期权判断需要期权费")
    answer = build_answer(request, body.kind, body.code, body.horizon, body.fee if body.kind == "option" else None)
    return request.app.state.judgments.seal(user.id, answer)


@router.get("")
def list_judgments(request: Request, user: User = Depends(current_user)):
    svc = request.app.state.judgments
    svc.settle(request.app.state.market.snapshot(), user.id)
    return {"items": svc.list(user.id), "record": svc.record(user.id)}


@router.get("/{jid}")
def get_judgment(jid: int, request: Request, user: User = Depends(current_user)):
    svc = request.app.state.judgments
    svc.settle(request.app.state.market.snapshot(), user.id)
    try:
        return svc.get(user.id, jid)
    except KeyError as exc:
        raise HTTPException(404, "判断不存在") from exc
