"""选股名单的服务：有哪些策略、每天去取名单、给页面和角色提供名单与战绩。

加一个新策略：在 STRATEGIES 里加一项，并在 _FETCHERS 里登记它怎么取名单。
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import threading

from ..data.ifind import IFindClient
from ..data.ifind_sync import CN_TZ, client_from_env
from ..data.store import MarketStore
from . import stats
from .store import PickStore
from .wencai import ask, parse_sjm, sjm_query

log = logging.getLogger("sixiang.picks")

STRATEGIES = {
    "sjm": {
        "id": "sjm", "name": "竞价先锋", "alias": "三角猫", "publish_at": "09:25",
        "tagline": "开盘前 5 分钟，挑出集合竞价里抢得最凶的 10 只。",
        "rules": [
            "只看主板和创业板，不要 ST、科创板、北交所，也不要新股次新股",
            "昨天没涨停，换手不到 5%，成交量没有比前一天翻倍——昨天还算安静",
            "总市值 500 亿以下，流通市值 10 亿以上",
            "今天集合竞价没有直接封死涨停",
            "按 09:25 竞价结束时的涨幅，从高到低取前 10 只",
        ],
    },
}


def recent_trade_days(client: IFindClient, before: dt.date, lookback: int = 20) -> list[dt.date]:
    """before 之前最近的交易日（升序）。用上证指数的日线日期来认交易日。"""
    start = before - dt.timedelta(days=lookback)
    frames = client.history(["sh000001"], start.isoformat(), (before - dt.timedelta(days=1)).isoformat(), "close")
    frame = frames.get("sh000001")
    return sorted(d for d in (frame.date if frame is not None else []) if d < before)


def fetch_sjm(client: IFindClient, day: dt.date, prev: dt.date, prev2: dt.date) -> list[dict]:
    rows = parse_sjm(ask(client, sjm_query(day, prev, prev2)), day, prev)
    # 不是交易日、或者竞价数据还没出来时，问财给不出 09:25 的涨幅——当作“今天没有名单”
    return rows if any(r["auction_pct"] is not None for r in rows) else []


_FETCHERS = {"sjm": fetch_sjm}


def _clean(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):
        return _clean(v.item())
    return v


class PickService:
    def __init__(self, store: PickStore, market: MarketStore):
        self.store, self.market = store, market
        self._cache: dict[tuple, dict] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------- 取名单
    def fetch(self, strategy: str, day: dt.date, client: IFindClient | None = None) -> int:
        """取某一天的名单并存库，返回只数。day 可以是今天，也可以是过去的交易日。"""
        client = client or client_from_env()
        prev = recent_trade_days(client, day)
        if len(prev) < 2:
            raise RuntimeError(f"{day} 前面找不到两个交易日")
        rows = _FETCHERS[strategy](client, day, prev[-1], prev[-2])
        if rows:
            self.store.save(strategy, day.isoformat(), rows)
        return len(rows)

    # ---------------------------------------------------------- 读
    def _enriched(self, strategy: str):
        snap, cur = self.market._current()
        key = (strategy, snap.version_id, self.store.stamp(strategy))
        with self._lock:
            hit = self._cache.get(key)
            if hit is None:
                m = stats.enrich(cur, self.store.rows(strategy))
                hit = {"frame": m, "summary": stats.summarize(cur, m) if len(m) else {"range": None}}
                self._cache = {key: hit}      # 只留最新的一份
        return snap, hit

    def strategies(self) -> list[dict]:
        out = []
        for sid, meta in STRATEGIES.items():
            _, hit = self._enriched(sid)
            days = sorted(self.store.days(sid))
            out.append({**meta, "latest_date": days[-1] if days else None, "headline": self._headline(hit["summary"])})
        return out

    @staticmethod
    def _headline(s: dict) -> dict | None:
        if not s.get("range"):
            return None
        return {"days": s["range"]["days"], "start": s["range"]["start"], "end": s["range"]["end"],
                "sealed_rate": s["overall"]["sealed_rate"], "market_sealed_rate": (s["baseline"]["market"] or {}).get("sealed_rate"),
                "any_sealed_rate": s["per_day"]["any_sealed_rate"], "intraday_mean": s["overall"]["intraday_mean"]}

    def day(self, strategy: str, date: str | None = None) -> dict:
        """某一天的名单（默认最近一天），每只带上当天的结果；行情还没到的那天结果为空。"""
        meta = STRATEGIES[strategy]
        snap, hit = self._enriched(strategy)
        m = hit["frame"]
        days = sorted(d for d, n in self.store.days(strategy).items() if n)
        today = dt.datetime.now(CN_TZ)
        date = date or (days[-1] if days else None)
        items = []
        if date and len(m):
            cols = ["rank", "code", "name", "board", "auction_pct", "limit_price", "open", "close", "open_pct", "day_pct",
                    "intraday", "sealed", "touched", "next_open_ret", "next_date"]
            for r in m[m.date == date].sort_values("rank")[cols].to_dict("records"):
                r = {k: _clean(v) for k, v in r.items()}
                r["auction_pct"] = r["auction_pct"] / 100 if r["auction_pct"] is not None else None   # 问财给的是百分数
                r["settled"] = r["open"] is not None
                r["sealed"], r["touched"] = (bool(r["sealed"]), bool(r["touched"])) if r["settled"] else (None, None)
                items.append(r)
        return {"strategy": meta, "date": date, "items": items, "days": days[-120:], "data_end": snap.data_end,
                "today": today.date().isoformat(), "is_today": date == today.date().isoformat(),
                "settled": bool(items) and all(i["settled"] for i in items)}

    def summary(self, strategy: str) -> dict:
        _, hit = self._enriched(strategy)
        return {"strategy": STRATEGIES[strategy], **_clean_tree(hit["summary"])}

    def of_stock(self, code: str) -> dict | None:
        """这只股票最近一次名单里有没有它（给个股页、群聊用）。"""
        for sid, meta in STRATEGIES.items():
            days = sorted(d for d, n in self.store.days(sid).items() if n)
            if not days:
                continue
            row = next((r for r in self.store.rows(sid, days[-1]) if r["code"] == code), None)
            if row:
                _, hit = self._enriched(sid)
                return {"strategy": sid, "name": meta["name"], "alias": meta["alias"], "date": days[-1], "rank": row["rank"],
                        "auction_pct": row["auction_pct"] / 100 if row.get("auction_pct") is not None else None, "headline": self._headline(hit["summary"])}
        return None


def _clean_tree(v):
    if isinstance(v, dict):
        return {k: _clean_tree(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean_tree(x) for x in v]
    return _clean(v)


class PickSchedule:
    """每个工作日到点去取当天的名单；没取到就隔一分钟再试几次。启动时如果今天已过点还没取，补一次。

    启用：环境变量 SIXIANG_PICKS_AT=09:25:40（北京时间），并配好 iFinD 凭证。
    """
    RETRIES, GAP = 8, 60

    def __init__(self, service: PickService, at: str):
        parts = [int(x) for x in at.split(":")]
        self.at = dt.time(*(parts + [0])[:3])
        self.service = service
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="picks", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _next(self, now: dt.datetime) -> dt.datetime:
        t = now.replace(hour=self.at.hour, minute=self.at.minute, second=self.at.second, microsecond=0)
        if t <= now:
            t += dt.timedelta(days=1)
        while t.weekday() >= 5:
            t += dt.timedelta(days=1)
        return t

    def _run(self) -> None:
        today = dt.datetime.now(CN_TZ).date()
        for sid in STRATEGIES:
            if today.isoformat() in self.service.store.days(sid):
                continue
            for attempt in range(self.RETRIES):
                try:
                    n = self.service.fetch(sid, today)
                    log.info("%s %s 名单 %d 只", sid, today, n)
                    if n:
                        break
                except Exception:  # noqa: BLE001  取不到不影响别的功能，页面上显示“今天的名单还没出”
                    log.exception("%s %s 取名单失败", sid, today)
                if self._stop.wait(self.GAP):
                    return

    def _loop(self) -> None:
        now = dt.datetime.now(CN_TZ)
        if now.weekday() < 5 and now.time() >= self.at:
            self._run()
        while not self._stop.is_set():
            target = self._next(dt.datetime.now(CN_TZ))
            if self._stop.wait((target - dt.datetime.now(CN_TZ)).total_seconds()):
                return
            self._run()
