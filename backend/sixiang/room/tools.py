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
