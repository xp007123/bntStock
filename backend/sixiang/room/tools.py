"""数据工具：把现有的引擎函数登记成角色可以调用的工具。

每个工具返回三样：text（给模型看的大白话，带关键数字）、card（给前端画数据卡，可以没有）、ok。
约定：工具不抛异常。取不到就返回 ok=False 和一句“这次没取到”，角色自己圆。
所有角色都能用所有工具；角色卡里的 tools 只是“爱用的”，不是限制。
加一种数据（产业链、新闻、外部 MCP）= 在这里登记一条，别处不用动。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..analysis.distribution import analyze, load, load_index
from ..analysis.narrative import horizon_text


@dataclass
class ToolResult:
    ok: bool
    text: str
    card: dict | None = None


@dataclass
class ToolContext:
    """工具运行时能拿到的东西。store 是行情库；jobs_root 是方法库任务的目录（只读）。"""
    store: Any
    jobs_root: Path | None = None
    cache: dict = field(default_factory=dict)      # 同一个群里，同样的调用只算一次
    picks: Any = None                              # 选股名单服务（没接上时相关工具回“取不到”）


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., ToolResult]

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict, required: list[str] | None = None):
    def deco(fn):
        REGISTRY[name] = Tool(name, description, {"type": "object", "properties": properties, "required": required or []}, fn)
        return fn
    return deco


def schemas(names: list[str] | None = None) -> list[dict]:
    return [t.schema() for n, t in REGISTRY.items() if names is None or n in names]


def run(ctx: ToolContext, name: str, args: dict) -> ToolResult:
    """执行一个工具。任何异常都变成 ok=False，不往外抛。"""
    t = REGISTRY.get(name)
    if t is None:
        return ToolResult(False, f"没有叫 {name} 的数据。")
    key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
    if key in ctx.cache:
        return ctx.cache[key]
    try:
        result = t.handler(ctx, **{k: v for k, v in args.items() if k in t.parameters["properties"]})
    except Exception as exc:
        result = ToolResult(False, f"这次没取到数据（{type(exc).__name__}）。")
    if result.ok:
        ctx.cache[key] = result
    return result


# ---------------------------------------------------------------- 小工具

P = lambda v, d=0: f"{v * 100:.{d}f}%"                       # noqa: E731
S = lambda v, d=1: f"{'+' if v > 0 else ''}{v * 100:.{d}f}%"  # noqa: E731

_H = {"type": "integer", "description": "看多久，单位是交易日：5=1周，21=1个月，63=3个月，126=半年。默认 21"}
_CODE = {"type": "string", "description": "股票代码或名称，如 sz002594、600519、比亚迪"}


def resolve(ctx: ToolContext, code: str) -> str:
    """模型给的可能是 sz002594、002594、比亚迪：都认。认不出就抛 KeyError，由 run() 接住。"""
    q = str(code).strip().lower().replace(".", "")
    snap = ctx.store.snapshot()
    for cand in (q, q[-2:] + q[:-2] if q[-2:] in ("sh", "sz", "bj") else q):
        if cand in snap.row_groups:
            return cand
    hits = ctx.store.search(q, limit=1)
    if hits:
        return hits[0]["code"]
    raise KeyError(code)


def _horizon(h) -> int:
    try:
        return max(1, min(250, int(h)))
    except (TypeError, ValueError):
        return 21


# ---------------------------------------------------------------- 工具

@tool("stock_outlook", "查一只股票接下来一段时间涨的可能有多大：和现在走势相似的历史时候，后来是涨是跌、平均涨跌多少、运气最差的一成会亏多少；并对照它不挑时候的情况。",
      {"code": _CODE, "horizon": _H}, ["code"])
def stock_outlook(ctx: ToolContext, code: str, horizon: int = 21) -> ToolResult:
    h = _horizon(horizon)
    a = analyze(load(ctx.store.snapshot(), resolve(ctx, code)), h)
    sim, base = a["similar"], a["all"]
    text = (f"{a['name']}，截至 {a['asof']} 收盘 {a['close']:.2f}。历史上和现在走势相似的 {sim['n']} 个时候，{horizon_text(h)}后在涨的占 {P(sim['up_prob'])}"
            f"（它不挑时候是 {P(base['up_prob'])}），平均 {S(sim['mean'])}，一半情况好于 {S(sim['median'])}，"
            f"运气最差的一成亏 {P(abs(sim['p10']), 1)} 以上，最好的一成赚 {P(sim['p90'], 1)} 以上。只是历史统计。")
    return ToolResult(True, text, {"type": "outlook", "code": a["code"], "name": a["name"], "horizon": h, "asof": a["asof"],
                                   "prob": sim["up_prob"], "base_prob": base["up_prob"], "mean": sim["mean"],
                                   "p10": sim["p10"], "p90": sim["p90"], "n": sim["n"]})


@tool("stock_recent", "查一只股票最近的走势：近 1 周、1 个月、3 个月涨跌，离一年内高点和低点多远，最近成交是放量还是缩量，波动大不大。",
      {"code": _CODE}, ["code"])
def stock_recent(ctx: ToolContext, code: str) -> ToolResult:
    c = resolve(ctx, code)
    sf = load(ctx.store.snapshot(), c)
    df = sf.df
    close = df.close
    ret = lambda n: float(close.iloc[-1] / close.iloc[-1 - n] - 1) if len(close) > n else None  # noqa: E731
    year = close.iloc[-250:]
    off_high, off_low = float(close.iloc[-1] / year.max() - 1), float(close.iloc[-1] / year.min() - 1)
    vol_ratio = float(df.volume.iloc[-5:].mean() / df.volume.iloc[-60:].mean()) if len(df) >= 60 and df.volume.iloc[-60:].mean() else None
    r5, r20, r60 = ret(5), ret(20), ret(60)
    day = float(close.iloc[-1] / close.iloc[-2] - 1) if len(close) > 1 else 0.0
    sector = ctx.store.security(c).get("sector") or "未分类"
    parts = [f"{sf.name}（{sector}），{df.date.iloc[-1]:%Y-%m-%d} 收盘 {float(df.raw_close.iloc[-1]):.2f}，当天 {S(day, 2)}"]
    parts.append("；".join(f"近{n}{S(v)}" for n, v in (("1周", r5), ("1个月", r20), ("3个月", r60)) if v is not None))
    parts.append(f"比一年内最高点低 {P(abs(off_high))}，比最低点高 {P(off_low)}")
    if vol_ratio is not None:
        parts.append(f"最近 5 天成交量是前 60 天均量的 {vol_ratio:.1f} 倍（{'放量' if vol_ratio > 1.3 else '缩量' if vol_ratio < 0.7 else '量能平平'}）")
    return ToolResult(True, "。".join(parts) + "。",
                      {"type": "recent", "code": c, "name": sf.name, "sector": sector, "date": f"{df.date.iloc[-1]:%Y-%m-%d}",
                       "close": float(df.raw_close.iloc[-1]), "day": day, "r5": r5, "r20": r20, "r60": r60,
                       "off_high": off_high, "off_low": off_low, "vol_ratio": vol_ratio})


@tool("stock_financials", "查一家公司的基本面和估值：市盈率、市净率、总市值、负债率，最近一期营收和净利润的同比增长。",
      {"code": _CODE}, ["code"])
def stock_financials(ctx: ToolContext, code: str) -> ToolResult:
    c = resolve(ctx, code)
    fin = ctx.store.financials(c)
    name = ctx.store.security(c)["name"]
    v = fin.get("valuation") if fin.get("available") else None
    if not v:
        return ToolResult(False, f"{name} 暂时没有财务数据。")
    latest = fin["reports"][0] if fin.get("reports") else None
    yoy = (latest or {}).get("yoy", {})
    rev = yoy.get("R_operating_total_revenue", yoy.get("R_revenue"))
    np_ = yoy.get("R_np_atoopc")
    pe = "亏损，算不出市盈率" if v.get("ttm_loss") else (f"市盈率（TTM）{v['pe_ttm']:.1f} 倍" if v.get("pe_ttm") else "市盈率暂缺")
    parts = [f"{name}：{pe}"]
    if v.get("pb"):
        parts.append(f"市净率 {v['pb']:.2f} 倍")
    if v.get("total_mcap"):
        parts.append(f"总市值 {v['total_mcap'] / 1e8:,.0f} 亿")
    if v.get("debt_ratio") is not None:
        parts.append(f"资产负债率 {P(v['debt_ratio'])}")
    if latest:
        growth = "，".join(f"{label}同比 {S(val, 0)}" for label, val in (("营收", rev), ("归母净利润", np_)) if val is not None)
        parts.append(f"最新一期（{latest['date']} 报告期，{latest['published']} 披露）{growth or '同比数据暂缺'}")
    return ToolResult(True, "，".join(parts) + f"。只用了 {fin['asof']} 之前已披露的财报。",
                      {"type": "financials", "code": c, "name": name, "asof": fin["asof"], "pe_ttm": v.get("pe_ttm"), "ttm_loss": bool(v.get("ttm_loss")),
                       "pb": v.get("pb"), "total_mcap": v.get("total_mcap"), "debt_ratio": v.get("debt_ratio"),
                       "report": latest and latest["date"], "revenue_yoy": rev, "profit_yoy": np_})


@tool("option_outlook", "查一个场外平值看涨期权值不值：按给定的期权费，历史上相似的时候能回本的比例，以及扣掉期权费后平均赚还是亏。",
      {"code": _CODE, "horizon": _H, "fee": {"type": "number", "description": "期权费，占本金的比例，如 0.075 表示 7.5%"}}, ["code", "fee"])
def option_outlook(ctx: ToolContext, code: str, fee: float, horizon: int = 63) -> ToolResult:
    h, fee = _horizon(horizon), float(fee)
    if fee > 1:
        fee /= 100           # 模型有时会把 7.5% 写成 7.5
    a = analyze(load(ctx.store.snapshot(), resolve(ctx, code)), h, fee)
    sim, base = a["similar"], a["all"]
    text = (f"{a['name']} {horizon_text(h)}平值看涨，期权费 {P(fee, 1)}：相似的 {sim['n']} 个时候里能回本的占 {P(sim['breakeven_prob'])}"
            f"（不挑时候是 {P(base['breakeven_prob'])}），扣掉期权费后平均 {S(sim['payoff_mean'])}，最差就是亏掉全部期权费。")
    return ToolResult(True, text, {"type": "option", "code": a["code"], "name": a["name"], "horizon": h, "fee": fee, "asof": a["asof"],
                                   "prob": sim["breakeven_prob"], "base_prob": base["breakeven_prob"], "payoff_mean": sim["payoff_mean"], "n": sim["n"]})


@tool("market_outlook", "查大盘现在什么状态：指数最近涨跌，以及历史上相似的时候之后涨的可能。",
      {"index": {"type": "string", "description": "指数代码，默认上证指数 sh000001；沪深300 是 sh000300，创业板指是 sz399006"}, "horizon": _H})
def market_outlook(ctx: ToolContext, index: str = "sh000001", horizon: int = 21) -> ToolResult:
    h = _horizon(horizon)
    code = str(index or "sh000001").strip().lower()
    a = analyze(load_index(ctx.store, code), h)
    st, sim, base = a["state"], a["similar"], a["all"]
    text = (f"{a['name']}，截至 {a['asof']} 收于 {a['close']:.2f}，近 20 个交易日 {S(st['r20'])}，比 60 日均线{'高' if st['pos60'] >= 0 else '低'} {P(abs(st['pos60']), 1)}。"
            f"历史上相似的 {sim['n']} 个时候，{horizon_text(h)}后在涨的占 {P(sim['up_prob'])}（不挑时候是 {P(base['up_prob'])}），平均 {S(sim['mean'])}。")
    return ToolResult(True, text, {"type": "outlook", "code": a["code"], "name": a["name"], "horizon": h, "asof": a["asof"], "index": True,
                                   "prob": sim["up_prob"], "base_prob": base["up_prob"], "mean": sim["mean"], "p10": sim["p10"], "p90": sim["p90"], "n": sim["n"]})


@tool("compare_stocks", "两只股票对着看：同样的期限，各自历史上相似的时候之后涨的可能，谁高谁低。",
      {"a": _CODE, "b": _CODE, "horizon": _H}, ["a", "b"])
def compare_stocks(ctx: ToolContext, a: str, b: str, horizon: int = 21) -> ToolResult:
    h = _horizon(horizon)
    snap = ctx.store.snapshot()
    rows = [analyze(load(snap, resolve(ctx, x)), h) for x in (a, b)]
    text = "；".join(f"{r['name']}：{horizon_text(h)}后在涨的占 {P(r['similar']['up_prob'])}（平时 {P(r['all']['up_prob'])}），平均 {S(r['similar']['mean'])}" for r in rows)
    return ToolResult(True, text + "。都是历史统计。",
                      {"type": "compare", "horizon": h, "items": [{"code": r["code"], "name": r["name"], "prob": r["similar"]["up_prob"],
                                                                  "base_prob": r["all"]["up_prob"], "mean": r["similar"]["mean"]} for r in rows]})


@tool("method_hits", "查这只股票今天符合方法库里的哪几种买法（放量突破、均线金叉、缩量回踩等），以及这些买法历史上出现之后大多怎么样。",
      {"code": _CODE}, ["code"])
def method_hits(ctx: ToolContext, code: str) -> ToolResult:
    c = resolve(ctx, code)
    name = ctx.store.security(c)["name"]
    snap = ctx.store.snapshot()
    if not ctx.jobs_root or not ctx.jobs_root.exists():
        return ToolResult(False, "方法库的结果现在取不到。")
    hits, checked = [], 0
    seen: set[str] = set()
    metas = []
    for p in ctx.jobs_root.glob("*/meta.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if m.get("system") and m.get("status") == "completed" and snap.same_market(m.get("data_version", "")):
            metas.append((m.get("created", ""), m, p.parent))
    for _, m, folder in sorted(metas, key=lambda x: x[0], reverse=True):
        if m["rule_hash"] in seen:
            continue
        seen.add(m["rule_hash"])
        try:
            r = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        checked += 1
        rows = [x for x in r.get("summary", []) if x.get("valid")]
        row = min(rows, key=lambda x: abs(x["horizon"] - 10)) if rows else None
        if any(s["code"] == c for s in r.get("selected", [])):
            hits.append({"method": m["name"], "horizon": row and row["horizon"], "win_rate": row and row["win_rate"],
                         "excess": row and row["excess_mean"], "events": r.get("deduplicated_events")})
    if not checked:
        return ToolResult(False, "方法库今天还没算好。")
    if not hits:
        return ToolResult(True, f"{name} 今天不符合方法库里 {checked} 种常见买法中的任何一种。", {"type": "methods", "code": c, "name": name, "checked": checked, "hits": []})
    desc = "；".join(f"“{x['method']}”（历史上出现 {x['events']:,} 次，之后 {x['horizon']} 天在涨的占 {P(x['win_rate'])}，比同一天随便买"
                    f"{'多赚' if (x['excess'] or 0) > 0 else '少赚'} {abs(x['excess'] or 0) * 100:.1f} 个百分点）" for x in hits)
    return ToolResult(True, f"{name} 今天符合：{desc}。", {"type": "methods", "code": c, "name": name, "checked": checked, "hits": hits})


@tool("pick_list", "查这只股票最近有没有进量化选股名单（比如“竞价先锋”：开盘前集合竞价抢得最凶的 10 只），以及这份名单过去当天涨停的比例。",
      {"code": {"type": "string", "description": "股票代码或名称"}}, ["code"])
def pick_list(ctx: ToolContext, code: str) -> ToolResult:
    c = resolve(ctx, code)
    name = ctx.store.security(c)["name"]
    if ctx.picks is None:
        return ToolResult(False, "选股名单现在取不到。")
    hit = ctx.picks.of_stock(c)
    if not hit:
        return ToolResult(True, f"{name} 不在最近一次的选股名单里。", {"type": "picks", "code": c, "name": name, "hit": None})
    h = hit.get("headline") or {}
    text = f"{name} 在 {hit['date']} 进了“{hit['name']}”名单，排第 {hit['rank']} 名"
    if hit.get("auction_pct") is not None:
        text += f"，集合竞价涨了 {S(hit['auction_pct'])}"
    if h:
        text += (f"。这份名单过去 {h['days']} 个交易日里：当天封住涨停的占 {P(h['sealed_rate'], 1)}（全市场是 {P(h['market_sealed_rate'] or 0, 1)}）")
    return ToolResult(True, text + "。", {"type": "picks", "code": c, "name": name, "hit": hit})


def _limit_ratio(code: str, name: str) -> float:
    """涨停幅度：创业板、科创板 20%，北交所 30%，ST 5%，其余 10%。"""
    if "ST" in (name or "").upper():
        return 1.05
    return 1.2 if code.startswith(("sz30", "sh68")) else 1.3 if code.startswith("bj") else 1.1


@tool("limit_up_history", "查这只股票过去三年涨停过多少次，它历史上涨停之后第二天、一周后大多怎么样，以及现在是不是在连板。聊涨停、打板、接力、第二天怎么走的时候用。",
      {"code": _CODE}, ["code"])
def limit_up_history(ctx: ToolContext, code: str) -> ToolResult:
    import pandas as pd
    c = resolve(ctx, code)
    raw = pd.DataFrame(ctx.store.daily(c, adjust="none", limit=750)["bars"])      # 认涨停用不复权的真实价格
    adj = pd.DataFrame(ctx.store.daily(c, adjust="qfq", limit=750)["bars"])       # 算之后的涨跌用前复权
    name = str(raw.name.iloc[-1])
    limit = [int(p * _limit_ratio(c, n) * 100 + 0.5 + 1e-6) / 100 for p, n in zip(raw.prev_close, raw.name)]
    up = (raw.close >= pd.Series(limit) - 0.001) & (raw.prev_close > 0)
    streak = 0
    for v in reversed(up.tolist()):
        if not v:
            break
        streak += 1
    nxt, week = adj.close.shift(-1) / adj.close - 1, adj.close.shift(-5) / adj.close - 1
    n, n1, n5 = int(up.sum()), nxt[up].dropna(), week[up].dropna()
    date = str(raw.date.iloc[-1])
    parts = [f"{name} 最近 {len(raw)} 个交易日里涨停过 {n} 次"]
    if len(n1):
        parts.append(f"涨停之后第二天收盘还在涨的有 {int((n1 > 0).sum())} 次（{P((n1 > 0).mean())}），第二天平均 {S(n1.mean())}"
                     + (f"；一周后平均 {S(n5.mean())}，还在涨的占 {P((n5 > 0).mean())}" if len(n5) else ""))
        if len(n1) < 10:
            parts.append("次数不多，只能当参考")
    parts.append(f"最新一天（{date}）是涨停，已经连着 {streak} 天涨停" if streak else f"最新一天（{date}）没有涨停")
    return ToolResult(True, "。".join(parts) + "。",
                      {"type": "limitup", "code": c, "name": name, "days": int(len(raw)), "n": n, "date": date, "streak": streak,
                       "next_n": int(len(n1)), "next_up": float((n1 > 0).mean()) if len(n1) else None, "next_mean": float(n1.mean()) if len(n1) else None,
                       "week_up": float((n5 > 0).mean()) if len(n5) else None, "week_mean": float(n5.mean()) if len(n5) else None})


@tool("sector_today", "查这只股票在它所属行业里的位置：最新一天这个行业多少只在涨、几只涨停、它的涨幅排第几、行业里涨得最多的是谁。聊板块、龙头、跟风、主线的时候用。",
      {"code": _CODE}, ["code"])
def sector_today(ctx: ToolContext, code: str) -> ToolResult:
    c = resolve(ctx, code)
    meta = ctx.store.security(c)
    sector = meta.get("sector")
    if not sector:
        return ToolResult(False, "这只股票没有行业分类，查不了板块。")
    _, cur = ctx.store._current()
    df = cur.execute("""SELECT d.code, d.name, d.close / d.prev_close - 1 AS pct FROM daily d JOIN securities s ON s.code = d.code
                        WHERE s.sector_l1 = ? AND CAST(d.date AS VARCHAR) = ? AND d.prev_close > 0 ORDER BY pct DESC""",
                     [sector, meta["last_date"]]).df()
    if c not in set(df.code):
        return ToolResult(False, "这只股票最新一天没有行情，查不了板块。")
    lim = sum(pct >= _limit_ratio(k, n) - 1 - 0.003 for k, n, pct in zip(df.code, df.name, df.pct))
    rank = int(df.index[df.code == c][0]) + 1
    mine = float(df.pct[df.code == c].iloc[0])
    name = str(df.name[df.code == c].iloc[0])
    top = [{"code": k, "name": n, "pct": float(p)} for k, n, p in zip(df.code[:3], df.name[:3], df.pct[:3])]
    text = (f"{name} 属于{sector}。{meta['last_date']} 这个行业 {len(df)} 只股票里 {int((df.pct > 0).sum())} 只上涨、{int(lim)} 只涨停，"
            f"涨幅居中的那只是 {S(float(df.pct.median()))}。{name} 当天 {S(mine)}，在行业里排第 {rank}。"
            f"涨得最多的：{'、'.join(t['name'] + ' ' + S(t['pct']) for t in top)}。")
    return ToolResult(True, text, {"type": "sector", "code": c, "name": name, "sector": sector, "date": meta["last_date"], "n": int(len(df)),
                                   "up": int((df.pct > 0).sum()), "limit": int(lim), "median": float(df.pct.median()), "pct": mine, "rank": rank, "top": top})


# ---------------------------------------------------------------- 来自 MCP 数据服务的（日线里没有的）
# 实时行情、概念、资金流、历史估值。没配 SIXIANG_MCP_MARKET_URL 时这几个工具回“取不到”，角色照常说话。

def _mcp():
    from ..data import mcp
    client = mcp.market()
    if client is None:
        raise LookupError("没有接 MCP 数据服务")
    return mcp, client


def _yi(v: float) -> str:
    return f"{'+' if v > 0 else ''}{v / 1e8:.2f} 亿"


def _now_cn():
    import datetime as dt
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))


_DULL_TAGS = {"深股通", "沪股通", "融资融券", "转融券标的", "标普道琼斯A股", "MSCI概念", "富时罗素概念", "富时罗素概念股"}


@tool("stock_live", "查一只股票此刻的实时行情：现价、今天涨跌幅、今天最高最低、成交额。盘中聊“现在怎么样”“今天走势”的时候用；收盘后拿到的是当天收盘的数。",
      {"code": _CODE}, ["code"])
def stock_live(ctx: ToolContext, code: str) -> ToolResult:
    mcp, _ = _mcp()
    c = resolve(ctx, code)
    q = mcp.quotes([c]).get(c)
    if not q:
        return ToolResult(False, "这只股票现在没有实时报价。")
    name = ctx.store.security(c)["name"]
    text = (f"{name} 现在 {q['latest']:.2f}" + (f"（今天 {S(q['change'], 2)}）" if q["change"] is not None else "")
            + (f"，今天最高 {q['high']:.2f}、最低 {q['low']:.2f}" if q.get("high") and q.get("low") else "")
            + (f"，成交 {q['amount'] / 1e8:.1f} 亿" if q.get("amount") else "") + f"。报价时间 {str(q.get('time') or '')[5:16]}。")
    return ToolResult(True, text, {"type": "live", "code": c, "name": name, **q})


@tool("stock_concepts", "查一只股票的细分行业和它身上的概念标签（比如“钛白粉概念”“宁德时代概念”）。聊题材、炒作逻辑、它算哪个板块的时候用。",
      {"code": _CODE}, ["code"])
def stock_concepts(ctx: ToolContext, code: str) -> ToolResult:
    mcp, client = _mcp()
    c = resolve(ctx, code)
    stocks = client.call("get_stock_reference", {"symbols": [mcp.symbol(c)]}, ttl=6 * 3600).get("stocks") or []
    if not stocks:
        return ToolResult(False, "没查到这只股票的概念。")
    s = stocks[0]
    tags = [t for t in s.get("concepts") or [] if t not in _DULL_TAGS]
    name = s.get("stockName") or ctx.store.security(c)["name"]
    text = f"{name} 的细分行业是{s.get('industry') or '未分类'}。" + (f"身上的概念：{'、'.join(tags[:10])}" + (f" 等 {len(tags)} 个。" if len(tags) > 10 else "。") if tags else "没有概念标签。")
    return ToolResult(True, text, {"type": "concepts", "code": c, "name": name, "industry": s.get("industry"), "concepts": tags[:12], "total": len(tags)})


@tool("money_flow", "查一只股票最近 5 个交易日的资金流向：每天资金净流入多少。聊主力、资金进出、有没有人在买的时候用。",
      {"code": _CODE}, ["code"])
def money_flow(ctx: ToolContext, code: str) -> ToolResult:
    import datetime as dt
    mcp, client = _mcp()
    c = resolve(ctx, code)
    today = _now_cn().date()
    data = client.call("get_daily_money_flow", {"symbols": [mcp.symbol(c)], "startDate": (today - dt.timedelta(days=14)).isoformat(), "endDate": today.isoformat(),
                                                "orderSize": "ALL", "metrics": ["ths_net_inflow_amt_stock"]}, ttl=120)
    days = [{"date": b["tradeDate"], "net": b.get("ths_net_inflow_amt_stock"), "big": b.get("ths_dde_stock")} for b in data.get("bars") or []]
    days = [d for d in days if d["net"] is not None][-5:]
    if not days:
        return ToolResult(False, "这只股票最近没有资金流数据。")
    name = ctx.store.security(c)["name"]
    net = sum(d["net"] for d in days)
    bigs = [d["big"] for d in days if d["big"] is not None]
    last = days[-1]
    text = (f"{name} 最近 {len(days)} 个交易日资金净流入合计 {_yi(net)}，其中 {sum(d['net'] > 0 for d in days)} 天是净流入"
            + (f"；大单净额合计 {_yi(sum(bigs))}" if bigs else "")
            + f"。最新一天（{last['date'][5:]}）净流入 {_yi(last['net'])}" + (f"，大单净额 {_yi(last['big'])}" if last["big"] is not None else "") + "。口径是同花顺的。")
    return ToolResult(True, text, {"type": "flow", "code": c, "name": name, "days": days, "net": net, "big": sum(bigs) if bigs else None})


@tool("hot_concepts", "查今天哪些概念板块最强：涨幅最大的几个、主力资金流入最多的几个。聊今天的主线、热点、资金去哪了的时候用。", {}, [])
def hot_concepts(ctx: ToolContext) -> ToolResult:
    _, client = _mcp()
    now = _now_cn()
    data = client.call("get_cn_sector_snapshot", {"asOf": now.isoformat(timespec="seconds"), "asOfSlot": "POST_MARKET", "topN": 5}, ttl=60)
    r = data.get("rankings") or {}
    up = [{"name": x["name"], "value": x["value"] / 100} for x in r.get("topGainers") or []]
    inflow = [{"name": x["name"], "value": x["value"]} for x in r.get("topMainNetInflows") or []]
    if not up and not inflow:
        return ToolResult(False, "今天的概念板块排名还没有。")
    text = (f"今天的概念板块（{str(data.get('latestQuoteTime') or '')[5:16]}，共 {data.get('universeCount')} 个）。"
            + (f"涨得最多的：{'、'.join(x['name'] + ' ' + S(x['value']) for x in up)}。" if up else "")
            + (f"主力资金流入最多的：{'、'.join(x['name'] + ' ' + _yi(x['value']) for x in inflow)}。" if inflow else ""))
    return ToolResult(True, text, {"type": "boards", "time": data.get("latestQuoteTime"), "up": up, "inflow": inflow})


@tool("valuation_position", "查一只股票现在的市盈率、市净率，在它自己最近一年多里算高还是低（比多少比例的日子高）。聊估值贵不贵、便不便宜的时候用。",
      {"code": _CODE}, ["code"])
def valuation_position(ctx: ToolContext, code: str) -> ToolResult:
    import datetime as dt
    mcp, client = _mcp()
    c = resolve(ctx, code)
    today = _now_cn().date()
    data = client.call("get_stock_valuation_history", {"symbols": [mcp.symbol(c)], "startDate": (today - dt.timedelta(days=495)).isoformat(),
                                                       "endDate": today.isoformat(), "metrics": ["PE_TTM", "PB_LATEST"]}, ttl=3600)
    bars = data.get("bars") or []
    name = ctx.store.security(c)["name"]
    parts, card = [], {"type": "valuation", "code": c, "name": name, "days": len(bars)}
    for key, label, field in (("PE_TTM", "市盈率", "pe"), ("PB_LATEST", "市净率", "pb")):
        vals = [b[key] for b in bars if b.get(key) is not None]
        if len(vals) < 60:
            continue
        now = vals[-1]
        if now <= 0:
            parts.append(f"{label}是负的（亏损），没法比高低")
            continue
        pos = sum(v < now for v in vals if v > 0) / max(1, sum(v > 0 for v in vals))
        parts.append(f"{label} {now:.1f} 倍，比最近 {len(vals)} 个交易日里 {P(pos)} 的日子高（这段时间最低 {min(v for v in vals if v > 0):.1f}、最高 {max(vals):.1f}）")
        card.update({field: now, f"{field}_pos": pos, f"{field}_min": min(v for v in vals if v > 0), f"{field}_max": max(vals)})
    if not parts:
        return ToolResult(False, "这只股票的历史估值数据不够。")
    return ToolResult(True, f"{name}：" + "；".join(parts) + "。", card)
