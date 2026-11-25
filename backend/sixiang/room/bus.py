"""消息总线：运行器往里发，打开着这个群的页面（SSE 连接）从里收。

现在是进程内存里的队列，够单进程用。以后开多进程，把这个文件换成 Redis 的发布订阅，接口不变。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict


class Bus:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, room_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._subs[room_id].add(q)
        return q

    def unsubscribe(self, room_id: int, q: asyncio.Queue) -> None:
        self._subs[room_id].discard(q)
        if not self._subs[room_id]:
            self._subs.pop(room_id, None)

    def publish(self, room_id: int, event: dict) -> None:
        for q in list(self._subs.get(room_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:      # 这个页面太久没读：丢掉它，页面重连时会从数据库补
                self._subs[room_id].discard(q)
