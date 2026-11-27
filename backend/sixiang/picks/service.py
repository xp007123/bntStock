"""选股名单的服务：有哪些策略、每天去取名单、给页面和角色提供名单与战绩。

加一个新策略：在 STRATEGIES 里加一项，并在 _FETCHERS 里登记它怎么取名单。

STRATEGIES 里的内容会原样发给页面，所以只放能给用户看的（名字、一句话介绍、几点出名单）。
具体的筛选条件是平台自己的东西，只留在 wencai.py 的问句里，不进接口、不上页面。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import threading
from functools import lru_cache
from pathlib import Path

from ..data import mcp
from ..data.ifind import IFindClient
from ..data.ifind_sync import CN_TZ, client_from_env
from ..data.store import MarketStore
from . import stats, wenge
from .store import PickStore
from .wencai import ask, parse_sjm, sjm_query

log = logging.getLogger("sixiang.picks")

# record：策略页第二个标签页叫什么、放什么。stats = 名单的历史统计；sim = 仿真模拟盘
STRATEGIES = {
    "sjm": {
        "id": "sjm", "name": "竞价先锋", "alias": "三角猫", "publish_at": "09:25", "record": "stats", "record_label": "历史表现",
        "tagline": "开盘前 5 分钟，挑出集合竞价里抢得最凶的 10 只。",
    },
    "wenge": {
        "id": "wenge", "name": "趋势之王", "alias": "文", "publish_at": "09:26", "record": "sim", "record_label": "仿真模拟盘",
        "tagline": "看公司质地、做中线的一份名单，开盘后出。",
    },
}

SIM_FILE = Path(__file__).parent / "data" / "wenge_sim.json"


@lru_cache(maxsize=1)
def sim() -> dict:
    """文哥的仿真模拟盘：旧四象回测引擎按平台的买卖规则在历史行情上模拟交易的每日净值（一次性导出，不再变）。"""
    return json.loads(SIM_FILE.read_text(encoding="utf-8"))


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
    if not s.get("range"):
        return []
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


def _span(m: dict) -> str:
    return f"{m['start'][:7].replace('-', '.')} 到 {m['end'][:7].replace('-', '.')}"


def _wenge_highlights(_s: dict) -> list[dict]:
    """趋势之王的主打数字：累计收益、年化、回撤（都是仿真模拟盘的，页面上在区块标题注明一次）。"""
    m = sim()
    hs = next((b for b in m["benchmarks"] if b["code"] == "sh000300"), None)
    full = [y for y in m["years"] if not y["partial"]]
    yearly = "、".join(f"{y['year']} {y['ret']:+.0%}" for y in full)
    return [{"label": "累计收益", "value": m["summary"]["total_return"], "note": _span(m) + (f"，同期沪深300 {hs['total']:+.0%}" if hs else "")},
            {"label": "年化收益", "value": m["summary"]["annualized"], "note": yearly + ("，年年为正" if all(y["ret"] > 0 for y in m["years"]) else "")},
            {"label": "最大回撤", "value": m["summary"]["max_drawdown"], "note": f"同期沪深300 最大回撤 {hs['max_drawdown']:.0%}" if hs else "从高点最多回落的幅度"}]


def _wenge_facts(_s: dict) -> list[str]:
    m = sim()
    full = [y for y in m["years"] if not y["partial"]]
    out = [f"仿真模拟盘 {m['start'][:4]} 年以来累计 {m['summary']['total_return']:+.0%}，最大回撤 {m['summary']['max_drawdown']:.1%}"]
    if full and all(y["ret"] > 0 for y in m["years"]):
        out.append("、".join(f"{y['year']} 年 {y['ret']:+.0%}" for y in full) + "，每年都是赚的")
    return out


def _wenge_report(items: list[dict], settled: bool, s: dict) -> dict:
    """趋势类不讲当天收盘：讲近一个月入选的票里，入选以来涨得最好的几只。全是已经发生的行情。"""
    note = f"最高涨幅 = 入选后 {FOLLOW_DAYS} 个交易日内的最高价比入选当天开盘价高多少。名单按平台的固定规则筛出，不是买卖建议。"
    best = s.get("best") or []
    stars = [{"rank": i + 1, "code": b["code"], "name": b["name"], "value": b["max"], "tag": None} for i, b in enumerate(best)]
    if best and best[0]["max"] > 0:
        top = best[0]
        return {"mode": "result", "title": f"{top['name']} 入选后最高涨过 {top['max']:.0%}",
                "big": {"num": f"+{top['max'] * 100:.0f}", "unit": "%", "label": f"{top['name']} 入选后最高涨过"},
                "sub": "近一个月入选的票里，涨得最好的几只", "value_label": "入选后最高涨过", "stars": stars, "note": note}
    n = len(items)
    return {"mode": "list", "title": f"名单 {n} 只", "big": None, "sub": "开盘后入选", "value_label": "开盘涨幅",
            "stars": [_star(i, None, "open_pct") for i in items], "note": note}


FOLLOW_DAYS = 20        # 趋势类名单最多跟踪 20 个交易日（策略平均拿 12 天左右）


HEAT = (15, 40)         # 当天入选不到 15 只算偏冷，超过 40 只算偏热（按 2024 年以来的分布定的）


def _streaks(m):
    """连续入选第几天：按出名单的日子数，中间断一天就重新数。"""
    if m.empty:
        return m.assign(streak=[])
    order = {d: i for i, d in enumerate(sorted(m.date.unique()))}
    m = m.sort_values(["code", "date"]).copy()
    pos = m.date.map(order)
    run = (pos.groupby(m.code).diff() != 1).cumsum()
    m["streak"] = m.groupby(run).cumcount() + 1
    return m


def _level(n: int) -> str:
    return "cold" if n < HEAT[0] else "hot" if n > HEAT[1] else "normal"


def _heat_history(m) -> dict:
    """每一档（偏冷 / 正常 / 偏热）在历史上：这样的日子有多少个，之后 20 个交易日那批票整体上涨的占多少。只算已经走完 20 天的。"""
    x = m[m.since_days >= FOLLOW_DAYS]
    if x.empty:
        return {}
    day = x.groupby("date").agg(n=("code", "size"), r=("since_ret", "mean"))
    out = {}
    for lv in ("cold", "normal", "hot"):
        d = day[day.n.map(_level) == lv]
        if len(d) >= 20:
            out[lv] = {"days": int(len(d)), "up_rate": float((d.r > 0).mean())}
    return out


def _best(m) -> list[dict]:
    """近 20 个出名单的日子里入选过的票，按入选后的最高涨幅排前 5。同一只票入选过好几次，按最早那次算。"""
    if m.empty:
        return []
    days = sorted(m.date.unique())[-FOLLOW_DAYS:]
    ok = m.skip.isna() if "skip" in m else True                    # 只算当天能开仓的
    x = m[m.date.isin(days) & m.since_max.notna() & ok].sort_values("date").drop_duplicates("code", keep="first")
    x = x.sort_values("since_max", ascending=False).head(5)
    return [{"code": r.code, "name": r.name, "date": r.date, "days": int(r.since_days), "max": float(r.since_max)} for r in x.itertuples()]


_VIEWS = {"sjm": {"highlights": _sjm_highlights, "facts": _sjm_facts, "report": _sjm_report},
          "wenge": {"highlights": _wenge_highlights, "facts": _wenge_facts, "report": _wenge_report}}


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
        self._pool_lock = threading.Lock()      # 候选池同一时间只算一份（启动补算和开盘出名单可能撞上）

    # ---------------------------------------------------------- 取名单
    def fetch(self, strategy: str, day: dt.date, client: IFindClient | None = None) -> int:
        """取某一天的名单并存库，返回只数。day 可以是今天，也可以是过去的交易日。"""
        client = client or client_from_env()
        if strategy == "wenge":
            rows = self._fetch_wenge(client, day)
        else:
            prev = recent_trade_days(client, day)
            if len(prev) < 2:
                raise RuntimeError(f"{day} 前面找不到两个交易日")
            rows = _FETCHERS[strategy](client, day, prev[-1], prev[-2])
        if rows:
            self.store.save(strategy, day.isoformat(), rows)
        return len(rows)

    # ---------------------------------------------------------- 文哥：每周的候选池 + 每天开盘后的判定
    @staticmethod
    def _monday(day: dt.date) -> dt.date:
        return day - dt.timedelta(days=day.weekday())

    def ensure_pool(self, client: IFindClient, day: dt.date, pool_date: dt.date | None = None) -> list[dict]:
        """day 所在那一周的候选池；库里没有就现算（全 A 拉一遍财务数，几分钟）。pool_date：用哪一天的股票池，默认这一周之前最近的交易日。"""
        monday = self._monday(day)
        with self._pool_lock:
            return self._ensure_pool(client, monday, pool_date)

    def _ensure_pool(self, client: IFindClient, monday: dt.date, pool_date: dt.date | None) -> list[dict]:
        pool = self.store.pool("wenge", monday.isoformat())
        if pool is None:
            pool_date = pool_date or recent_trade_days(client, monday)[-1]
            pool = wenge.prescreen(client, monday, monday + dt.timedelta(days=4), pool_date)
            if pool:
                self.store.save_pool("wenge", monday.isoformat(), pool)
        return pool

    def _fetch_wenge(self, client: IFindClient, day: dt.date, opens: dict[str, float] | None = None,
                     index_now: dict[str, float] | None = None) -> list[dict]:
        """当天的文哥名单。opens 不给就取实时开盘价（行情 MCP）；回填时传日线里的开盘价。index_now：三个板块指数现在的点位，同理。"""
        pool = self.ensure_pool(client, day)
        if not pool:
            return []
        codes = [p["code"] for p in pool]
        if opens is None:
            opens = {}
            try:
                opens = {c: q["open"] for c, q in mcp.quotes(codes, ttl=0).items() if q.get("open")}
            except Exception:  # noqa: BLE001
                log.exception("文哥：行情 MCP 取开盘价失败，改用 iFinD")
            if not opens:
                opens = wenge.realtime_open(client, codes)
        _, cur = self.market._current()
        rows = wenge.bullish(pool, wenge.past_closes(cur, codes, day), opens)
        skip = self.wenge_skips(cur, day, {r["code"]: r["open"] for r in rows}, index_now)
        # 存库的字段不能和日线的列重名（enrich 会再配一遍当天行情）
        return [{"rank": r["rank"], "code": r["code"], "name": r["name"], "pick_open": r["open"], "pick_open_pct": r["open_pct"],
                 "undistri": r["undistri"], "skip": skip.get(r["code"])} for r in rows]

    @staticmethod
    def wenge_skips(cur, day: dt.date, opens: dict[str, float], index_now: dict[str, float] | None = None) -> dict[str, str]:
        """入选的票里今天不开仓的：code → 原因（只存库备查）。指数点位取不到时，板块那一道不判。"""
        if not opens:
            return {}
        if index_now is None:
            index_now = {}
            try:
                index_now = {c: q.get("open") or q.get("latest") for c, q in mcp.quotes(list(wenge.BOARD_INDEX.values()), ttl=0).items()}
            except Exception:  # noqa: BLE001
                log.exception("文哥：取板块指数点位失败，今天不判板块那一道")
        return wenge.skip_reasons(wenge.prior_bars(cur, list(opens), day), opens, wenge.index_declining(cur, day, index_now))

    # ---------------------------------------------------------- 读
    def _enriched(self, strategy: str):
        snap, cur = self.market._current()
        key = (strategy, snap.version_id, self.store.stamp(strategy))
        with self._lock:
            hit = self._cache.get(key)
            if hit is None:
                m = stats.enrich(cur, self.store.rows(strategy))
                if STRATEGIES[strategy]["record"] == "sim":       # 趋势类：看入选之后，不看当天
                    m = _streaks(stats.follow(cur, m, FOLLOW_DAYS))
                    summary = {"range": None, "best": _best(m), "heat": _heat_history(m)}
                else:
                    summary = stats.summarize(cur, m) if len(m) else {"range": None}
                hit = {"frame": m, "summary": summary}
                self._cache = {k: v for k, v in self._cache.items() if k[0] != strategy} | {key: hit}   # 每个策略只留最新的一份
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
        return _clean_tree(_VIEWS[strategy]["highlights"](hit["summary"]))

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
                    "intraday", "sealed", "touched", "next_open_ret", "next_date", "pick_open_pct", "pick_open",
                    "since_days", "since_max", "streak", "skip"]
            for r in m[m.date == date].sort_values("rank").reindex(columns=cols).to_dict("records"):
                r = {k: _clean(v) for k, v in r.items()}
                r["auction_pct"] = r["auction_pct"] / 100 if r["auction_pct"] is not None else None   # 问财给的是百分数
                if r["open_pct"] is None:                       # 当天日线还没进来：先用出名单时的开盘涨幅
                    r["open_pct"] = r["pick_open_pct"]
                r.pop("pick_open_pct")
                r["pick_price"] = r.pop("pick_open") if r["open"] is None else r["open"]      # 入选价：当天开盘价
                r["no_open"] = bool(r.pop("skip"))                 # 今天不开仓。原因不出接口
                r["settled"] = r["open"] is not None
                r["sealed"], r["touched"] = (bool(r["sealed"]), bool(r["touched"])) if r["settled"] else (None, None)
                items.append(r)
        extra = {}
        if meta["record"] != "sim":
            for r in items:
                for k in ("pick_price", "since_days", "since_max", "streak", "no_open"):
                    r.pop(k, None)
        else:
            items.sort(key=lambda r: (r["no_open"], -(r["streak"] or 0), r["rank"]))   # 能开仓的在前；其中连续入选久的排前面
            level = _level(len(items))
            extra = {"follow_days": FOLLOW_DAYS, "best": hit["summary"].get("best", []),
                     "open_count": sum(not r["no_open"] for r in items),
                     "heat": {"count": len(items), "level": level, "history": hit["summary"].get("heat", {}).get(level)} if items else None}
        return {**extra, "strategy": meta, "date": date, "items": items, "days": days, "data_end": snap.data_end,
                "today": today.date().isoformat(), "is_today": date == today.date().isoformat(),
                "settled": bool(items) and all(i["settled"] for i in items)}

    def summary(self, strategy: str) -> dict:
        if STRATEGIES[strategy]["record"] == "sim":
            return {"strategy": STRATEGIES[strategy], "highlights": self.highlights(strategy), "kind": "sim", "sim": sim(),
                    "facts": _VIEWS[strategy]["facts"]({})}
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
                        "auction_pct": row["auction_pct"] / 100 if row.get("auction_pct") is not None else None, "headline": self._headline(hit["summary"]),
                        "facts": _VIEWS[sid]["facts"](hit["summary"]) if meta["record"] == "sim" else []}
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

    def __init__(self, service: PickService, at: str, strategies: list[str] | None = None):
        parts = [int(x) for x in at.split(":")]
        self.at = dt.time(*(parts + [0])[:3])
        self.service = service
        self.strategies = strategies or list(STRATEGIES)
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
        for sid in self.strategies:
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


class PoolSchedule:
    """文哥的候选池：每周五 16:30 算下一周的；启动时如果这一周的还没有，马上补一份（后台跑，几分钟）。

    和每日名单一起启用（设了 SIXIANG_PICKS_AT 才开）。时间可用 SIXIANG_WENGE_POOL_AT 改。
    """

    def __init__(self, service: PickService, at: str = "16:30"):
        h, m = (int(x) for x in at.split(":")[:2])
        self.at = dt.time(h, m)
        self.service = service
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="wenge-pool", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _build(self, day: dt.date, pool_date: dt.date | None = None) -> None:
        try:
            pool = self.service.ensure_pool(client_from_env(), day, pool_date)
            log.info("文哥候选池 %s 那一周：%d 只", day, len(pool))
        except Exception:  # noqa: BLE001  算不出来不影响别的；当天出名单时会再试一次
            log.exception("文哥候选池 %s 算失败", day)

    def _loop(self) -> None:
        now = dt.datetime.now(CN_TZ)
        self._build(now.date() + dt.timedelta(days=2) if now.weekday() >= 5 else now.date())   # 周末启动：补下一周的
        while not self._stop.is_set():
            now = dt.datetime.now(CN_TZ)
            t = now.replace(hour=self.at.hour, minute=self.at.minute, second=0, microsecond=0)
            days = (4 - now.weekday()) % 7
            t += dt.timedelta(days=days)
            if t <= now:
                t += dt.timedelta(days=7)
            if self._stop.wait((t - now).total_seconds()):
                return
            today = dt.datetime.now(CN_TZ).date()
            self._build(today + dt.timedelta(days=3), today)        # 周五收盘后：下一周的，股票池用今天的
