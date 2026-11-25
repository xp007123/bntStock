"""群的状态：话题、成员、消息。这里只有数据结构，不碰数据库；存取在 store.py（后面加）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    seq: int
    role: str                       # host 小四 / guest 嘉宾 / user 用户 / system 系统提示
    name: str
    text: str
    persona_id: str | None = None
    reply_to: int | None = None     # 回的是哪一条（seq）
    cards: list[dict] = field(default_factory=list)       # 挂的数据卡，由工具返回的数据画
    data: list[str] = field(default_factory=list)         # 这条消息查到的数据（大白话），后面的人能看到
    meta: dict = field(default_factory=dict)              # 模型、耗时、token、人设版本、有没有出过错


@dataclass
class Room:
    topic: dict                     # 第一版：{"kind": "stock", "code": ..., "name": ...}
    members: list[str]              # 嘉宾的 id，按座次
    user_name: str = "你"
    brief: str = ""                 # 话题简报：开群时取一次，所有人共用
    summary: str = ""               # 更早聊天记录的摘要
    messages: list[Message] = field(default_factory=list)

    def add(self, role: str, name: str, text: str, **kw) -> Message:
        m = Message(seq=len(self.messages) + 1, role=role, name=name, text=text, **kw)
        self.messages.append(m)
        return m

    def by_seq(self, seq: int | None) -> Message | None:
        return next((m for m in self.messages if m.seq == seq), None) if seq else None

    def last_by(self, persona_id: str) -> Message | None:
        return next((m for m in reversed(self.messages) if m.persona_id == persona_id), None)
