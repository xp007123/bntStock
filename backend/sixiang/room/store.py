"""群和消息的存取。只做读写，不含任何聊天逻辑。"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Engine

from ..auth.db import room_messages, rooms
from .state import Message, Room


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _j(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def message_dict(m: Message, created_at: dt.datetime | None = None) -> dict:
    """给前端的一条消息。meta 里只带展示用得上的，不带 token 数这些内部信息。"""
    return {"seq": m.seq, "role": m.role, "persona_id": m.persona_id, "name": m.name, "text": m.text, "reply_to": m.reply_to,
            "cards": m.cards, "action": m.meta.get("action"), "created_at": created_at.isoformat() if created_at else None}


class RoomStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        # 服务重启时还标着“演出中”的群，其实已经断了
        with engine.begin() as conn:
            conn.execute(update(rooms).where(rooms.c.status == "playing").values(status="interrupted"))

    def create(self, user_id: int, title: str, topic: dict, members: list[str]) -> int:
        with self.engine.begin() as conn:
            return conn.execute(insert(rooms).values(user_id=user_id, title=title[:80], topic_json=_j(topic), members_json=_j(members),
                                                     status="idle", created_at=_now(), updated_at=_now())).inserted_primary_key[0]

    def row(self, rid: int, user_id: int | None = None):
        q = select(rooms).where(rooms.c.id == rid)
        if user_id is not None:
            q = q.where(rooms.c.user_id == user_id)
        with self.engine.connect() as conn:
            r = conn.execute(q).first()
        if r is None:
            raise KeyError(rid)
        return r

    def info(self, r) -> dict:
        return {"id": r.id, "title": r.title, "topic": {k: v for k, v in json.loads(r.topic_json).items() if k != "brief"},
                "members": json.loads(r.members_json), "status": r.status, "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat()}

    def list(self, user_id: int, limit: int = 50) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(rooms).where(rooms.c.user_id == user_id).order_by(rooms.c.updated_at.desc()).limit(limit)).all()
            out = []
            for r in rows:
                last = conn.execute(select(room_messages.c.name, room_messages.c.text, room_messages.c.seq).where(room_messages.c.room_id == r.id)
                                    .order_by(room_messages.c.seq.desc()).limit(1)).first()
                out.append(self.info(r) | {"last": {"name": last.name, "text": last.text} if last else None, "count": last.seq if last else 0})
        return out

    def messages(self, rid: int, after: int = 0) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(room_messages).where(room_messages.c.room_id == rid, room_messages.c.seq > after).order_by(room_messages.c.seq)).all()
        return [message_dict(self._message(r), r.created_at) for r in rows]

    @staticmethod
    def _message(r) -> Message:
        return Message(seq=r.seq, role=r.role, name=r.name, text=r.text, persona_id=r.persona_id, reply_to=r.reply_to,
                       cards=json.loads(r.cards_json or "[]"), data=json.loads(r.data_json or "[]"), meta=json.loads(r.meta_json or "{}"))

    def load(self, rid: int, user_name: str) -> Room:
        """读成运行器用的 Room（含全部消息）。"""
        r = self.row(rid)
        topic = json.loads(r.topic_json)
        with self.engine.connect() as conn:
            rows = conn.execute(select(room_messages).where(room_messages.c.room_id == rid).order_by(room_messages.c.seq)).all()
        return Room(topic=topic, members=json.loads(r.members_json), user_name=user_name, brief=topic.get("brief", ""),
                    summary=r.summary or "", messages=[self._message(x) for x in rows])

    def append(self, rid: int, m: Message) -> dict:
        now = _now()
        with self.engine.begin() as conn:
            conn.execute(insert(room_messages).values(room_id=rid, seq=m.seq, role=m.role, persona_id=m.persona_id, name=m.name, text=m.text,
                                                      reply_to=m.reply_to, cards_json=_j(m.cards), data_json=_j(m.data), meta_json=_j(m.meta), created_at=now))
            conn.execute(update(rooms).where(rooms.c.id == rid).values(updated_at=now))
        return message_dict(m, now)

    def update(self, rid: int, **fields) -> None:
        if "members" in fields:
            fields["members_json"] = _j(fields.pop("members"))
        if "topic" in fields:
            fields["topic_json"] = _j(fields.pop("topic"))
        with self.engine.begin() as conn:
            conn.execute(update(rooms).where(rooms.c.id == rid).values(**fields))

    def said_by(self, user_id: int, persona_id: str, limit: int = 8) -> list[dict]:
        """这个角色最近在这位用户的群里说过的话（新的在前）。给角色个人页用。"""
        q = (select(room_messages.c.room_id, room_messages.c.seq, room_messages.c.text, room_messages.c.created_at, rooms.c.title)
             .select_from(room_messages.join(rooms, rooms.c.id == room_messages.c.room_id))
             .where(rooms.c.user_id == user_id, room_messages.c.persona_id == persona_id, room_messages.c.role == "guest")
             .order_by(room_messages.c.id.desc()).limit(limit))
        with self.engine.connect() as conn:
            return [{"room_id": r.room_id, "seq": r.seq, "text": r.text, "title": r.title, "created_at": r.created_at.isoformat()} for r in conn.execute(q)]

    def record_of(self, user_id: int, persona_id: str) -> dict:
        """这个角色在这位用户的群里一共说了多少条、聊过几只股票。给角色个人页用。"""
        q = (select(func.count(), func.count(func.distinct(rooms.c.title)))
             .select_from(room_messages.join(rooms, rooms.c.id == room_messages.c.room_id))
             .where(rooms.c.user_id == user_id, room_messages.c.persona_id == persona_id, room_messages.c.role == "guest"))
        with self.engine.connect() as conn:
            said, stocks = conn.execute(q).one()
        return {"said": said, "stocks": stocks}

    def spoken_today(self, user_id: int) -> int:
        """这个用户今天（UTC 日）群里的角色一共说了多少条。额度按这个数。"""
        start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(room_messages.join(rooms, rooms.c.id == room_messages.c.room_id))
                                .where(rooms.c.user_id == user_id, room_messages.c.role.in_(("host", "guest")),
                                       room_messages.c.created_at >= start)).scalar_one()
