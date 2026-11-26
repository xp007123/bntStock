"""房间运行器：演出和观看分开。

每个群同一时间只有一个后台任务在跑。开群、用户说话、接着聊，都只是往这个群的信箱里放一条指令；
任务按顺序处理，产生的每条消息先写数据库，再发到消息总线。页面刷新、断线都不影响演出。
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from . import actor, tools
from .bus import Bus
from .director import Roundtable
from .llm import ChatModel
from .registry import PersonaRegistry
from .store import RoomStore

log = logging.getLogger("sixiang.room")
MAX_MEMBERS = 6
LIMIT_LINE = "今天聊得够多了，嗓子都哑了。明天接着来。"
QUIET_LINE = "信号不太好，大家都没出声。过一会儿再点“让他们聊起来”试试。"


class RoomError(ValueError):
    pass


class RoomService:
    def __init__(self, store: RoomStore, registry: PersonaRegistry, market, jobs_root: Path, model: ChatModel | None, bus: Bus | None = None):
        self.store, self.registry, self.market, self.jobs_root, self.model = store, registry, market, jobs_root, model
        self.bus = bus or Bus()
        self.daily_limit = int(os.environ.get("SIXIANG_ROOM_DAILY_LIMIT", "300"))
        self._inbox: dict[int, list[dict]] = {}
        self._tasks: dict[int, asyncio.Task] = {}
        self._ctx: dict[int, tools.ToolContext] = {}
        self.picks = None      # 选股名单服务，由应用入口接上

    @property
    def available(self) -> bool:
        return self.model is not None

    # ---------------------------------------------------------- 指令（由接口调用）
    def _brief(self, code: str) -> tuple[str, str, str]:
        ctx = tools.ToolContext(self.market, self.jobs_root, picks=self.picks)
        code = tools.resolve(ctx, code)
        recent = tools.run(ctx, "stock_recent", {"code": code})
        name = recent.card["name"] if recent.card else self.market.security(code)["name"]
        picked = tools.run(ctx, "pick_list", {"code": code})      # 在选股名单里的话，开场就让大家知道
        extra = picked.text if picked.ok and picked.card and picked.card.get("hit") else ""
        return code, name, f"股票：{name}（{code}）。{recent.text if recent.ok else ''}{extra}"

    async def open(self, user, code: str, members: list[str] | None = None) -> int:
        if not self.available:
            raise RoomError("群聊还没开通")
        try:
            code, name, brief = await asyncio.to_thread(self._brief, code)
        except Exception as exc:
            raise RoomError(f"没找到这只股票：{code}") from exc
        cast = self.registry.cast()
        picked = [m for m in (members or self.registry.default_members()) if m in cast and cast[m].role == "guest"][:MAX_MEMBERS]
        if not picked:
            raise RoomError("群里至少要有一位嘉宾")
        rid = await asyncio.to_thread(self.store.create, user.id, name, {"kind": "stock", "code": code, "name": name, "brief": brief}, picked)
        self._enqueue(rid, user, {"kind": "open"})
        return rid

    def say(self, rid: int, user, text: str) -> None:
        text = text.strip()[:500]
        if not text:
            raise RoomError("说点什么吧")
        self._enqueue(rid, user, {"kind": "say", "text": text})

    def more(self, rid: int, user) -> None:
        self._enqueue(rid, user, {"kind": "more"})

    async def set_members(self, rid: int, user, add: str | None = None, remove: str | None = None) -> list[str]:
        row = await asyncio.to_thread(self.store.row, rid, user.id)
        import json
        members = json.loads(row.members_json)
        cast = self.registry.cast()
        note = None
        if add and add in cast and cast[add].role == "guest" and add not in members:
            if len(members) >= MAX_MEMBERS:
                raise RoomError(f"群里最多 {MAX_MEMBERS} 位嘉宾")
            members.append(add)
            note = f"{cast[add].name} 被拉进了群"
        if remove and remove in members:
            if len(members) <= 1:
                raise RoomError("群里至少要留一位嘉宾")
            members.remove(remove)
            note = f"{cast[remove].name if remove in cast else remove} 被请出了群"
        if note:
            await asyncio.to_thread(self.store.update, rid, members=members)
            self._enqueue(rid, user, {"kind": "note", "text": note, "members": members})
        return members

    def _enqueue(self, rid: int, user, cmd: dict) -> None:
        self._inbox.setdefault(rid, []).append(cmd | {"user": user})
        task = self._tasks.get(rid)
        if task is None or task.done():
            self._tasks[rid] = asyncio.get_running_loop().create_task(self._run(rid))

    # ---------------------------------------------------------- 运行器
    def _pub(self, rid: int, kind: str, **payload) -> None:
        self.bus.publish(rid, {"type": kind, **payload})

    async def _run(self, rid: int) -> None:
        try:
            while self._inbox.get(rid):
                cmd = self._inbox[rid].pop(0)
                try:
                    await self._handle(rid, cmd)
                except Exception:      # 任何意外都不让这个群卡死：记日志，结束这一场
                    log.exception("room %s: scene failed", rid)
                    self._pub(rid, "scene_end", status="idle")
            await asyncio.to_thread(self.store.update, rid, status="idle")
        finally:
            self._tasks.pop(rid, None)
            self._inbox.pop(rid, None) if not self._inbox.get(rid) else None

    async def _handle(self, rid: int, cmd: dict) -> None:
        user = cmd["user"]
        room = await asyncio.to_thread(self.store.load, rid, user.username)
        cast, host = self.registry.cast(), self.registry.host()

        async def keep(msg) -> None:
            self._pub(rid, "message", message=await asyncio.to_thread(self.store.append, rid, msg))

        if cmd["kind"] == "note":
            await keep(room.add("system", "系统", cmd["text"]))
            self._pub(rid, "members", members=cmd["members"])
            return
        user_msg = None
        if cmd["kind"] == "say":
            mentions = [p for p in room.members if p in cast and ("@" + cast[p].name) in cmd["text"]]
            user_msg = room.add("user", user.username, cmd["text"].replace("@", ""), meta={"mentions": mentions})
            await keep(user_msg)

        # 额度：只为管成本。用完了也是一句台词，不是报错
        if await asyncio.to_thread(self.store.spoken_today, user.id) >= self.daily_limit:
            await keep(room.add("host", host.name, LIMIT_LINE, persona_id=host.id, meta={"action": "limit"}))
            self._pub(rid, "scene_end", status="idle", limit=True)
            return

        director = Roundtable(cast, self.model)
        if cmd["kind"] == "open" or not any(m.role == "guest" for m in room.messages) and cmd["kind"] == "more":
            await self._refresh_brief(rid, room)
            scene = director.opening(room)
        elif cmd["kind"] == "say":
            scene = director.on_user(room, user_msg)
        else:
            await self._refresh_brief(rid, room)
            scene = director.more(room)

        await asyncio.to_thread(self.store.update, rid, status="playing")
        self._pub(rid, "status", status="playing")
        ctx = self._ctx.setdefault(rid, tools.ToolContext(self.market, self.jobs_root, picks=self.picks))

        async def emit(kind: str, payload: dict) -> None:
            if kind == "message":
                await keep(room.by_seq(payload["seq"]))
            elif kind in ("typing", "delta", "skipped"):
                self._pub(rid, kind, **{k: v for k, v in payload.items() if k != "errors"})
                if kind == "skipped" and payload.get("errors"):
                    log.warning("room %s: %s skipped: %s", rid, payload.get("persona"), payload["errors"])

        # 用户在一场戏中间说话：当前这条说完就停，先处理用户的话
        interrupted = lambda: any(c["kind"] == "say" for c in self._inbox.get(rid, []))  # noqa: E731
        made = await actor.play(scene, room, cast, host, self.model, ctx, emit, interrupted)
        if made == 0 and not interrupted():
            # 整场没有一个人说得出话（多半是模型连不上）：小四说一句固定的话，不让用户对着空群干等
            await keep(room.add("host", host.name, QUIET_LINE, persona_id=host.id, meta={"action": "quiet"}))
        self._pub(rid, "scene_end", status="idle")

    async def _refresh_brief(self, rid: int, room) -> None:
        """话题简报跟着最新行情走（隔天接着聊时，价格已经变了）。"""
        try:
            _, _, brief = await asyncio.to_thread(self._brief, room.topic["code"])
        except Exception:
            return
        if brief != room.brief:
            room.brief = brief
            self._ctx.pop(rid, None)
            await asyncio.to_thread(self.store.update, rid, topic=room.topic | {"brief": brief})

    def is_playing(self, rid: int) -> bool:
        t = self._tasks.get(rid)
        return bool(t and not t.done())
