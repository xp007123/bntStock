"""选股名单的服务：有哪些策略、每天去取名单、给页面和角色提供名单与战绩。

加一个新策略：在 STRATEGIES 里加一项，并在 _FETCHERS 里登记它怎么取名单。

STRATEGIES 里的内容会原样发给页面，所以只放能给用户看的（名字、一句话介绍、几点出名单）。
具体的筛选条件是平台自己的东西，只留在 wencai.py 的问句里，不进接口、不上页面。
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


# ---------------------------------------------------------------- 每个策略自己决定“拿什么说话”
# 首页看板、策略页顶上的几个数、分享的战报图，都从这里取。新策略各写各的，页面不用改。

def _sjm_highlights(s: dict) -> list[dict]:
    """竞价先锋的主打数字：封板。"""
    market = (s["baseline"]["market"] or {}).get("sealed_rate")
    top1 = next((b["sealed_rate"] for b in s["by_rank"] if b["label"] == "第 1 名"), None)
    out = [{"label": "当天封住涨停的", "value": s["overall"]["sealed_rate"], "note": f"同期全市场是 {market:.1%}" if market is not None else ""},
           {"label": "名单里至少有一只封板的日子", "value": s["per_day"]["any_sealed_rate"], "note": f"共 {s['range']['days']} 个交易日"}]
    if top1 is not None:
        out.append({"label": "排第 1 名的那只，封住涨停的", "value": top1, "note": "竞价涨幅最高的一只"})
    return out


def _sjm_facts(s: dict) -> list[str]:
    if not s.get("range"):
        return []
    days, rate = s["range"]["days"], s["overall"]["sealed_rate"]
    market = (s["baseline"]["market"] or {}).get("sealed_rate")
    out = []
    if market and rate / market >= 2:
        out.append(f"近 {days} 个交易日，涨停机会是全市场的 {rate / market:.0f} 倍")
    else:
        out.append(f"近 {days} 个交易日，{rate:.0%} 当天封住涨停")
    out.append(f"{s['per_day']['any_sealed_rate']:.0%} 的交易日，名单里至少有一只封板")
    return out


def _star(i: dict, tag: str | None, key: str = "day_pct") -> dict:
    return {"rank": i["rank"], "code": i["code"], "name": i["name"], "value": i[key], "tag": tag}


def _sjm_report(items: list[dict], settled: bool, s: dict) -> dict:
    """某一天的战报：讲这一天最亮的那件事。全部是当天已经发生的结果，一个数都不编。"""
    n = len(items)
    note = "封板指收盘价等于涨停价。名单按固定规则筛出，数字是历史统计。"
    if not settled:
        return {"mode": "list", "title": f"名单 {n} 只", "big": None, "sub": "按 09:25 的竞价涨幅排",
                "value_label": "竞价涨幅", "stars": [_star(i, None, "auction_pct") for i in items], "note": note}
    sealed = [i for i in items if i["sealed"]]
    touched = [i for i in items if i["touched"] and not i["sealed"]]
    stars = [_star(i, "封板") for i in sealed] + [_star(i, "摸过涨停") for i in touched]
    if sealed:
        title, big = f"{n} 只里 {len(sealed)} 只封住涨停", {"num": str(len(sealed)), "unit": "只", "label": "封住涨停"}
        sub = f"名单共 {n} 只" + (f"，另有 {len(touched)} 只盘中摸到过涨停" if touched else "")
    elif touched:
        title, big = f"{n} 只里 {len(touched)} 只盘中摸到涨停", {"num": str(len(touched)), "unit": "只", "label": "盘中摸到涨停"}
        sub = f"名单共 {n} 只"
    else:
        ups = sorted((i for i in items if (i["day_pct"] or 0) > 0), key=lambda i: -i["day_pct"])
        stars = [_star(i, None) for i in ups[:3]]
        if ups:
            title = f"{ups[0]['name']} 当天涨 {ups[0]['day_pct']:.1%}"
            big = {"num": f"+{ups[0]['day_pct'] * 100:.1f}", "unit": "%", "label": f"{ups[0]['name']} 当天涨幅"}
            sub = f"名单共 {n} 只，{len(ups)} 只收盘是涨的"
        elif s.get("range"):
            title = f"名单 {n} 只"
            big = {"num": f"{s['overall']['sealed_rate'] * 100:.0f}", "unit": "%", "label": f"近 {s['range']['days']} 个交易日封住涨停的比例"}
            sub = f"名单共 {n} 只"
        else:
            title, big, sub = f"名单 {n} 只", None, ""
    return {"mode": "result", "title": title, "big": big, "sub": sub, "value_label": "当天收盘", "stars": stars[:6], "note": note}


_VIEWS = {"sjm": {"highlights": _sjm_highlights, "facts": _sjm_facts, "report": _sjm_report}}


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
            out.append({**meta, "latest_date": days[-1] if days else None, "headline": self._headline(hit["summary"]),
                        "highlights": self.highlights(sid), "latest": self.report(sid) if days else None})
        return out

    def highlights(self, strategy: str) -> list[dict]:
        _, hit = self._enriched(strategy)
        s = hit["summary"]
        return _clean_tree(_VIEWS[strategy]["highlights"](s)) if s.get("range") else []

    def report(self, strategy: str, date: str | None = None) -> dict:
        """某一天的战报（默认最近一天）：首页看板和分享图用。还没收盘的那天只有名单。"""
        d = self.day(strategy, date)
        _, hit = self._enriched(strategy)
        view = _VIEWS[strategy]
        body = view["report"](d["items"], d["settled"], hit["summary"]) if d["items"] else {
            "mode": "empty", "title": "还没有名单", "big": None, "sub": "", "value_label": "", "stars": [], "note": ""}
        return _clean_tree({"strategy": d["strategy"], "date": d["date"], "is_today": d["is_today"], "today": d["today"],
                            "count": len(d["items"]), **body, "facts": view["facts"](hit["summary"])})

    @staticmethod
    def _headline(s: dict) -> dict | None:
        if not s.get("range"):
            return None
        return {"days": s["range"]["days"], "start": s["range"]["start"], "end": s["range"]["end"],
                "sealed_rate": s["overall"]["sealed_rate"], "market_sealed_rate": (s["baseline"]["market"] or {}).get("sealed_rate"),
                "any_sealed_rate": s["per_day"]["any_sealed_rate"],
                "top1_sealed_rate": next((b["sealed_rate"] for b in s["by_rank"] if b["label"] == "第 1 名"), None)}

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
        return {"strategy": meta, "date": date, "items": items, "days": days, "data_end": snap.data_end,
                "today": today.date().isoformat(), "is_today": date == today.date().isoformat(),
                "settled": bool(items) and all(i["settled"] for i in items)}

    def summary(self, strategy: str) -> dict:
        _, hit = self._enriched(strategy)
        return {"strategy": STRATEGIES[strategy], "highlights": self.highlights(strategy), **_clean_tree(hit["summary"])}

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
