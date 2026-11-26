"""名单存取。"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Engine

from ..auth.db import pick_days, picks


class PickStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save(self, strategy: str, date: str, rows: list[dict]) -> None:
        """整天覆盖写入（同一天重取一次，以新的为准）。"""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        with self.engine.begin() as conn:
            conn.execute(delete(picks).where(picks.c.strategy == strategy, picks.c.date == date))
            conn.execute(delete(pick_days).where(pick_days.c.strategy == strategy, pick_days.c.date == date))
            conn.execute(insert(pick_days).values(strategy=strategy, date=date, count=len(rows), fetched_at=now))
            for r in rows:
                detail = {k: v for k, v in r.items() if k not in ("code", "name", "rank")}
                conn.execute(insert(picks).values(strategy=strategy, date=date, code=r["code"], name=r["name"][:40], rank=r["rank"],
                                                  detail_json=json.dumps(detail, ensure_ascii=False)))

    def days(self, strategy: str) -> dict[str, int]:
        """取过名单的日子 → 那天几只。"""
        with self.engine.connect() as conn:
            rows = conn.execute(select(pick_days.c.date, pick_days.c.count).where(pick_days.c.strategy == strategy)).all()
        return {r.date: r.count for r in rows}

    def stamp(self, strategy: str) -> str:
        """名单有没有变过的记号（给战绩缓存用）。"""
        with self.engine.connect() as conn:
            rows = conn.execute(select(pick_days.c.date, pick_days.c.fetched_at).where(pick_days.c.strategy == strategy)).all()
        return f"{len(rows)}:{max((str(r.fetched_at) for r in rows), default='')}"

    def rows(self, strategy: str, date: str | None = None) -> list[dict]:
        q = select(picks).where(picks.c.strategy == strategy)
        if date:
            q = q.where(picks.c.date == date)
        with self.engine.connect() as conn:
            found = conn.execute(q.order_by(picks.c.date, picks.c.rank)).all()
        return [{"date": r.date, "code": r.code, "name": r.name, "rank": r.rank, **json.loads(r.detail_json or "{}")} for r in found]

    def strategies_of(self, code: str, date: str) -> list[str]:
        """这只股票在这一天进了哪些名单。"""
        with self.engine.connect() as conn:
            return [r.strategy for r in conn.execute(select(picks.c.strategy).where(picks.c.code == code, picks.c.date == date)).all()]
