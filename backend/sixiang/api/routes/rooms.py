"""群聊接口：角色列表、开群、看消息、说话、接着聊、拉人踢人，以及流式推送（SSE）。

约定：没有“错误事件”。演出里出的任何问题都在后台变成一句台词或被跳过；接口只在请求本身不对时报错
（没登录、群不是你的、股票没找到）。
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...auth.deps import current_user
from ...auth.service import User
from ...room.personas import DISCLAIMER
from ...room.service import RoomError, RoomService

router = APIRouter(prefix="/api", tags=["rooms"])


def _svc(request: Request) -> RoomService:
    return request.app.state.rooms


def _own(request: Request, rid: int, user: User):
    try:
        return _svc(request).store.row(rid, user.id)
    except KeyError as exc:
        raise HTTPException(404, "没有这个群") from exc


@router.get("/personas")
def list_personas(request: Request):
    """我们有哪些角色（给角色页和头像用）。available 为假表示群聊还没开通（没配模型）。"""
    svc = _svc(request)
    reg = svc.registry
    return {"available": svc.available, "host": reg.host().public(), "items": [p.public() for p in reg.guests()],
            "default": reg.default_members(), "disclaimer": DISCLAIMER}


class OpenBody(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    members: list[str] | None = None


@router.post("/rooms")
async def open_room(body: OpenBody, request: Request, user: User = Depends(current_user)):
    try:
        return {"id": await _svc(request).open(user, body.code, body.members)}
    except RoomError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/rooms")
def list_rooms(request: Request, user: User = Depends(current_user)):
    return {"items": _svc(request).store.list(user.id)}


@router.get("/rooms/{rid}")
def get_room(rid: int, request: Request, user: User = Depends(current_user)):
    svc = _svc(request)
    row = _own(request, rid, user)
    return svc.store.info(row) | {"messages": svc.store.messages(rid), "playing": svc.is_playing(rid)}


class SayBody(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.post("/rooms/{rid}/say")
async def say(rid: int, body: SayBody, request: Request, user: User = Depends(current_user)):
    _own(request, rid, user)
    try:
        _svc(request).say(rid, user, body.text)
    except RoomError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.post("/rooms/{rid}/continue")
async def more(rid: int, request: Request, user: User = Depends(current_user)):
    _own(request, rid, user)
    svc = _svc(request)
    if not svc.is_playing(rid):
        svc.more(rid, user)
    return {"ok": True}


class MembersBody(BaseModel):
    add: str | None = None
    remove: str | None = None


@router.post("/rooms/{rid}/members")
async def members(rid: int, body: MembersBody, request: Request, user: User = Depends(current_user)):
    _own(request, rid, user)
    try:
        return {"members": await _svc(request).set_members(rid, user, body.add, body.remove)}
    except RoomError as exc:
        raise HTTPException(422, str(exc)) from exc


def _sse(event: dict, eid: int | None = None) -> str:
    head = f"id: {eid}\n" if eid is not None else ""
    return f"{head}data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/rooms/{rid}/stream")
async def stream(rid: int, request: Request, after: int = 0, user: User = Depends(current_user)):
    """先补发 after 之后已经存下来的消息，再接着推新的。浏览器断线重连时会带上 Last-Event-ID。"""
    _own(request, rid, user)
    svc = _svc(request)
    last = request.headers.get("last-event-id")
    start = int(last) if last and last.isdigit() else after

    async def gen():
        q = svc.bus.subscribe(rid)       # 先订阅再补发，中间不会漏
        try:
            seen = start
            for m in await asyncio.to_thread(svc.store.messages, rid, start):
                seen = m["seq"]
                yield _sse({"type": "message", "message": m}, m["seq"])
            yield _sse({"type": "status", "status": "playing" if svc.is_playing(rid) else "idle"})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"        # 保持连接
                    continue
                if ev["type"] == "message":
                    if ev["message"]["seq"] <= seen:
                        continue
                    seen = ev["message"]["seq"]
                    yield _sse(ev, seen)
                else:
                    yield _sse(ev)
        finally:
            svc.bus.unsubscribe(rid, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})   # 让 nginx 不要攒着发
