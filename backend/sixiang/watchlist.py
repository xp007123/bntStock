"""自选股：每个用户关注的股票清单。只存代码，行情和小四的看法在读取时现算。"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .auth.db import watchlist

MAX_ITEMS = 30


class WatchlistFull(ValueError):
    pass


class Watchlist:
    def __init__(self, engine: Engine):
        self.engine = engine

    def codes(self, user_id: int) -> list[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(watchlist.c.code).where(watchlist.c.user_id == user_id).order_by(watchlist.c.id)).all()
        return [r.code for r in rows]

    def add(self, user_id: int, code: str) -> None:
        with self.engine.begin() as conn:
            n = conn.execute(select(func.count()).select_from(watchlist).where(watchlist.c.user_id == user_id)).scalar_one()
            if n >= MAX_ITEMS:
                raise WatchlistFull(f"自选最多 {MAX_ITEMS} 只，先删掉几只再加")
            try:
                conn.execute(insert(watchlist).values(user_id=user_id, code=code,
                                                      created_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)))
            except IntegrityError:
                pass  # 已经在自选里

    def remove(self, user_id: int, code: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(watchlist).where(watchlist.c.user_id == user_id, watchlist.c.code == code))
