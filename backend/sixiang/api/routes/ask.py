"""问个股、问期权、问大盘、两只对比（结构化提问）：数字来自收益分布引擎，文字由规则生成。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ...analysis.distribution import NotEnoughHistory, analyze, load, load_index, series
from ...analysis.narrative import compare_answer, option_answer, stock_answer
from ...data.store import NoDataVersion, UnknownSecurity

router = APIRouter(prefix="/api/ask", tags=["ask"])


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
                 "source": f"收益分布引擎 · 数据 {snap.version_id} · 截至 {a['asof']}"}]
    if valuation:
        pe = "亏损" if valuation.get("ttm_loss") else (f"{valuation['pe_ttm']:.1f}" if valuation.get("pe_ttm") else "—")
        pb = f"{valuation['pb']:.2f}" if valuation.get("pb") else "—"
        yoy = latest["yoy"].get("R_np_atoopc") if latest else None
        evidence.append({"role": "基本面与估值",
                         "text": f"市盈率 TTM {pe}，市净率 {pb}" + (f"；最新一期归母净利润同比 {'+' if yoy >= 0 else '−'}{abs(yoy) * 100:.0f}%" if yoy is not None else "") + "。",
                         "source": f"财务报告 · {fin['asof']} 前已披露" + (f"（{latest['date']} 报告期）" if latest else "")})
    return {"kind": kind, "code": a["code"], "name": a["name"], "horizon": horizon, "fee": fee,
            "asof": a["asof"], "close": a["close"], "data_version": snap.version_id, "market_version": snap.market_version,
            "analysis": a, **text, "evidence": evidence,
            "pending_evidence": (["市场环境（成交量、涨跌家数）"] if kind == "index" else
                                 ["事件与风险（财报日、解禁、新闻）", "市场环境（大盘与板块）"])}


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
