"""问个股、问期权、问大盘、两只对比（结构化提问）：数字来自收益分布引擎，文字由规则生成。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ...analysis.distribution import NotEnoughHistory, analyze, load, load_index, series
from ...analysis.narrative import compare_answer, horizon_text, option_answer, stock_answer
from ...data.store import NoDataVersion, UnknownSecurity
from ...room import tools as room_tools

router = APIRouter(prefix="/api/ask", tags=["ask"])


def _environment(store, code: str, horizon: int) -> dict | None:
    """大盘和板块现在什么状态。和群聊角色查的是同一套数（同一个引擎、同一个工具），取不到就不放这一条。"""
    parts = []
    try:
        m = analyze(load_index(store, "sh000001"), horizon)
        st, sim, base = m["state"], m["similar"], m["all"]
        parts.append(f"上证指数近 20 个交易日 {st['r20'] * 100:+.1f}%，在 60 日均线{'上方' if st['pos60'] >= 0 else '下方'} {abs(st['pos60']) * 100:.1f}%；"
                     f"大盘走成这样的时候，{horizon_text(horizon)}后在涨的占 {sim['up_prob'] * 100:.0f}%（平时 {base['up_prob'] * 100:.0f}%）")
    except Exception:  # noqa: BLE001
        pass
    sector = room_tools.run(room_tools.ToolContext(store), "sector_today", {"code": code})
    if sector.ok and sector.card:
        c = sector.card
        parts.append(f"所在的{c['sector']}行业最新一天 {c['n']} 只里 {c['up']} 只上涨、{c['limit']} 只涨停，它当天 {c['pct'] * 100:+.1f}%，排第 {c['rank']}")
    return {"role": "大盘与板块", "text": "。".join(parts) + "。", "source": "收益分布引擎 · 全市场日线"} if parts else None


def build_answer(request: Request, kind: str, code: str, horizon: int, fee: float | None) -> dict:
    store = request.app.state.market
    try:
        snap = store.snapshot()
        sf = load_index(store, code.lower()) if kind == "index" else load(snap, code.lower())
        a = analyze(sf, horizon, fee)
        fin = {"available": False} if kind == "index" else store.financials(code.lower())
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, UnknownSecurity) as exc:
        raise HTTPException(404, f"未找到 {code}") from exc
    except (NotEnoughHistory, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    valuation = fin.get("valuation") if fin.get("available") else None
    text = (option_answer(a, valuation) if kind == "option" else
            stock_answer(a, None, subject="指数") if kind == "index" else stock_answer(a, valuation))
    latest = fin["reports"][0] if fin.get("reports") else None
    evidence = [{"role": "走势与概率", "text": f"{horizon} 个交易日的涨跌分布：全部历史 {a['all']['n']:,} 个起点，其中和现在最相似的 {a['similar']['n']} 个。",
                 "source": "收益分布引擎 · 2007 年以来的日线"}]
    if valuation:
        pe = "亏损" if valuation.get("ttm_loss") else (f"{valuation['pe_ttm']:.1f}" if valuation.get("pe_ttm") else "—")
        pb = f"{valuation['pb']:.2f}" if valuation.get("pb") else "—"
        yoy = latest["yoy"].get("R_np_atoopc") if latest else None
        evidence.append({"role": "基本面与估值",
                         "text": f"市盈率 TTM {pe}，市净率 {pb}" + (f"；最新一期归母净利润同比 {'+' if yoy >= 0 else '−'}{abs(yoy) * 100:.0f}%" if yoy is not None else "") + "。",
                         "source": "财务报告" + (f" · {latest['date']} 报告期" if latest else "")})
    if kind != "index":
        env = _environment(store, a["code"], horizon)
        if env:
            evidence.append(env)
    return {"kind": kind, "code": a["code"], "name": a["name"], "horizon": horizon, "fee": fee,
            "asof": a["asof"], "close": a["close"], "data_version": snap.version_id, "market_version": snap.market_version,
            "analysis": a, **text, "evidence": evidence,
            "pending_evidence": []}      # 还没做的不往页面上摆


@router.get("/stock")
def ask_stock(request: Request, code: str, horizon: int = Query(20, ge=1, le=250)):
    return build_answer(request, "stock", code, horizon, None)


@router.get("/option")
def ask_option(request: Request, code: str, horizon: int = Query(63, ge=5, le=250), fee: float = Query(..., gt=0, lt=1)):
    return build_answer(request, "option", code, horizon, fee)


@router.get("/index")
def ask_index(request: Request, code: str, horizon: int = Query(21, ge=1, le=250)):
    return build_answer(request, "index", code, horizon, None)


@router.get("/compare")
def ask_compare(request: Request, a: str, b: str, horizon: int = Query(21, ge=1, le=250)):
    if a.lower() == b.lower():
        raise HTTPException(422, "请选两只不同的股票")
    left, right = build_answer(request, "stock", a, horizon, None), build_answer(request, "stock", b, horizon, None)
    return {"horizon": horizon, "asof": left["asof"], "data_version": left["data_version"],
            "items": [left, right], **compare_answer(left["analysis"], right["analysis"])}


@router.get("/series")
def ask_series(request: Request, code: str, index: bool = False):
    """走势图用的收盘序列（和问答用同一份数据）。"""
    store = request.app.state.market
    try:
        snap = store.snapshot()
        sf = load_index(store, code.lower()) if index else load(snap, code.lower())
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, UnknownSecurity) as exc:
        raise HTTPException(404, f"未找到 {code}") from exc
    return {**series(sf), "data_version": snap.version_id}


# 体检：从几个角度看同一只票。每一项就是群聊角色用的那个数据工具，取不到的那项不显示。
CHECKUP = ["stock_live", "stock_news", "valuation_position", "profit_forecast", "stock_financials", "method_hits", "limit_up_history",
           "sector_today", "stock_concepts", "money_flow", "dragon_tiger", "lockup", "pick_list"]
CHECKUP_HORIZONS = [5, 10, 21, 63]


@router.get("/checkup")
def ask_checkup(request: Request, code: str):
    """问个股的“体检”：几个期限一起看（概率 + 大概落在什么价位），加上估值、买点、涨停、行业、概念、资金几个角度。"""
    store = request.app.state.market
    try:
        sf = load(store.snapshot(), code.lower())
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    except (KeyError, UnknownSecurity) as exc:
        raise HTTPException(404, f"未找到 {code}") from exc
    horizons = []
    for h in CHECKUP_HORIZONS:
        try:
            a = analyze(sf, h)
        except (NotEnoughHistory, ValueError):
            continue
        sim = a["similar"]
        horizons.append({"horizon": h, "label": horizon_text(h), "prob": sim["up_prob"], "base": a["all"]["up_prob"], "median": sim["median"],
                         "p10": sim["p10"], "p90": sim["p90"], "low": a["close"] * (1 + sim["p10"]), "high": a["close"] * (1 + sim["p90"]), "close": a["close"]})
    rooms = request.app.state.rooms
    ctx = room_tools.ToolContext(store, rooms.jobs_root, picks=getattr(request.app.state, "picks", None))
    items = []
    for name in CHECKUP:
        r = room_tools.run(ctx, name, {"code": sf.code})
        if r.ok and r.card and not (name == "pick_list" and not r.card.get("hit")):
            items.append({"tool": name, "text": r.text, "card": r.card})
    return {"code": sf.code, "name": sf.name, "horizons": horizons, "items": items}


MARKET_ENV = ["market_today", "market_breadth", "us_overnight", "hot_concepts", "hot_stocks"]


@router.get("/market-env")
def ask_market_env(request: Request):
    """问大盘的“现在的市场环境”：今天的指数、涨跌家数、隔夜美股、最强的概念、人气股。取不到的那项不显示。"""
    try:
        ctx = room_tools.ToolContext(request.app.state.market)
        ctx.store.snapshot()
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    items = []
    for name in MARKET_ENV:
        r = room_tools.run(ctx, name, {})
        if r.ok and r.card:
            items.append({"tool": name, "text": r.text, "card": r.card})
    return {"items": items}
