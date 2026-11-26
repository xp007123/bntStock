"""管理端 · 角色管理：看有哪些角色、改人设（每保存一次多一个版本）、切回旧版或出厂设置、停用、设默认和座次、新建，
以及“试说一句”——用正在编辑的草稿让角色对一只股票说句话，不用保存就能看效果。仅管理员可用。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...auth.deps import require_admin
from ...auth.service import User
from ...room import actor, skills, tools
from ...room.director import Host, Solo, Speak
from ...room.registry import PersonaError, PersonaRegistry, validate
from ...room.state import Room

router = APIRouter(prefix="/api/admin/personas", tags=["admin"], dependencies=[Depends(require_admin)])

TEMPLATE = """---
id: new_persona
name: 新角色
title: 一句话介绍这个人
lens: 看什么
tagline: 一句代表性的话
bio: 两句话的概要简介：这个人是谁，凭什么值得听（给不认识他的用户看）
color: #7f8c9b
tools: [stock_outlook, stock_financials]
rivals: [buffett]
temperature: 0.9
version: 1
---
## 你是谁

## 信条
-

## 看一只股票的顺序
1.

## 不碰什么
-

## 爱看的数据

## 说话方式
-

## 和别人的典型分歧
-

## 示例发言
-
"""


def _reg(request: Request) -> PersonaRegistry:
    return request.app.state.rooms.registry


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, "没有这个角色或这个版本") from exc
    except PersonaError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def list_all(request: Request):
    return {"items": _reg(request).admin_list(), "tools": [{"name": t.name, "description": t.description} for t in tools.REGISTRY.values()],
            "template": TEMPLATE, "available": request.app.state.rooms.available}


@router.get("/{pid}")
def detail(pid: str, request: Request):
    return _guard(_reg(request).detail, pid)


@router.get("/{pid}/versions/{version}")
def version(pid: str, version: int, request: Request):
    """看某一版的全文。version 传 0 表示出厂设置。"""
    return {"version": version, "content": _guard(_reg(request).version_content, pid, version or None)}


class SaveBody(BaseModel):
    content: str = Field(min_length=20, max_length=40000)
    note: str = Field(default="", max_length=200)


@router.post("")
def create(body: SaveBody, request: Request, user: User = Depends(require_admin)):
    return _guard(_reg(request).save, None, body.content, body.note or "新建", user.id)


@router.post("/{pid}/versions")
def save(pid: str, body: SaveBody, request: Request, user: User = Depends(require_admin)):
    return _guard(_reg(request).save, pid, body.content, body.note, user.id)


class UseBody(BaseModel):
    version: int | None = None       # 空 = 回到出厂设置


@router.post("/{pid}/use")
def use(pid: str, body: UseBody, request: Request):
    return _guard(_reg(request).use_version, pid, body.version)


class SettingsBody(BaseModel):
    enabled: bool | None = None
    in_default: bool | None = None
    sort: int | None = Field(default=None, ge=0, le=999)


@router.post("/{pid}/settings")
def settings(pid: str, body: SettingsBody, request: Request):
    return _guard(_reg(request).configure, pid, body.enabled, body.in_default, body.sort)


@router.get("/{pid}/deep")
def deep_pack(pid: str, request: Request):
    """这位角色的深聊包：出处、哪一种、多长、有哪些小节和资料，以及装配后真正进提示词的正文。"""
    pack = _reg(request).deep_pack(pid, full=True)
    if pack is None:
        raise HTTPException(404, "这位角色还没有装深聊包")
    return pack


class DeepBody(BaseModel):
    enabled: bool


@router.post("/{pid}/deep")
def set_deep(pid: str, body: DeepBody, request: Request):
    """开 / 关这位角色的一对一深聊。关掉后用户看不到入口；已经开始的深聊还能接着聊。"""
    return _guard(_reg(request).set_deep, pid, body.enabled)


class TryDeepBody(BaseModel):
    code: str = Field(default="sh600519", max_length=20)
    say: str = Field(default="", max_length=300)


@router.post("/{pid}/deep/try")
async def try_deep(pid: str, body: TryDeepBody, request: Request):
    """试聊一轮深聊：他开场；填了 say 就再回应一句。真的调用模型，要等十几秒到半分钟。返回内容和花了多少。"""
    svc = request.app.state.rooms
    if not svc.available:
        raise HTTPException(503, "还没有配置模型，没法试聊")
    cast = svc.registry.cast()
    if pid not in cast or skills.load(pid) is None:
        raise HTTPException(404, "这位角色还没有装深聊包")
    try:
        code, name, brief = await asyncio.to_thread(svc._brief, body.code)
    except Exception as exc:
        raise HTTPException(422, f"没找到这只股票：{body.code}") from exc
    room = Room(topic={"kind": "stock", "code": code, "name": name, "mode": "deep"}, members=[pid], user_name="用户", brief=brief)
    director, ctx = Solo(cast), tools.ToolContext(svc.market, svc.jobs_root, picks=svc.picks)
    await actor.play(director.opening(room), room, cast, svc.registry.host(), svc.model, ctx)
    if body.say.strip():
        await actor.play(director.on_user(room, room.add("user", "用户", body.say.strip())), room, cast, svc.registry.host(), svc.model, ctx)
    said = [m for m in room.messages if m.role == "guest"]
    if not said:
        return {"ok": False, "note": "这次没说出话来（模型没回应）。再试一次。"}
    total = lambda k: sum(int(m.meta.get(k, 0) or 0) for m in said)  # noqa: E731
    return {"ok": True, "stock": name, "turns": [{"role": m.role, "name": m.name, "text": m.text, "data": m.data} for m in room.messages],
            "usage": {"seconds": round(sum(float(m.meta.get("seconds", 0) or 0) for m in said), 1), "calls": total("calls"),
                      "prompt_tokens": total("prompt_tokens"), "cached_tokens": total("cached_tokens"), "completion_tokens": total("completion_tokens")}}


class TryBody(BaseModel):
    content: str = Field(min_length=20, max_length=40000)
    code: str = Field(default="sh600519", max_length=20)
    cue: str = Field(default="", max_length=300)


@router.post("/try")
async def try_out(body: TryBody, request: Request):
    """用草稿试说一句（不保存）。真的调用模型，所以要等几秒。"""
    svc = request.app.state.rooms
    if not svc.available:
        raise HTTPException(503, "还没有配置模型，没法试说")
    try:
        me = validate(body.content)
    except PersonaError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        code, name, brief = await asyncio.to_thread(svc._brief, body.code)
    except Exception as exc:
        raise HTTPException(422, f"没找到这只股票：{body.code}") from exc
    cast = svc.registry.cast() | {me.id: me}
    host = me if me.role == "host" else svc.registry.host()
    room = Room(topic={"kind": "stock", "code": code, "name": name}, members=[me.id] if me.role == "guest" else svc.registry.default_members(),
                user_name="用户", brief=brief)
    step = (Host("open", body.cue or f"开场。用一句话说今天聊 {name}，然后点一位嘉宾先说。") if me.role == "host"
            else Speak(me.id, body.cue or "小四点你先说。按你自己看股票的顺序，说你的第一反应。想看数据就先查。"))
    msg = await actor.perform(step, room, cast, host, svc.model, tools.ToolContext(svc.market, svc.jobs_root, picks=svc.picks))
    if msg is None:
        return {"ok": False, "text": "", "note": "这次没说出话来（模型没回应）。再试一次。"}
    return {"ok": True, "text": msg.text, "data": msg.data, "cards": msg.cards, "stock": name, "seconds": msg.meta.get("seconds")}
