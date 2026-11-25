"""自选股：清单增删，以及“小四今天怎么看”（每只股票接下来 1 个月上涨的历史概率，对照它平时的概率）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ...analysis.distribution import NotEnoughHistory, analyze, load
from ...auth.deps import current_user
from ...auth.service import User
from ...data.store import NoDataVersion
from ...watchlist import WatchlistFull

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

HORIZON = 21   # 1 个月，和首页“问个股”的常用期限一致
_cache: dict[tuple[str, str], dict] = {}   # (数据版本, 代码) → 一行；行情更新后版本号变化，自然失效


def _row(snap, code: str) -> dict:
    key = (snap.version_id, code)
    if key in _cache:
        return _cache[key]
    sf = load(snap, code)
    df = sf.df
    row = {"code": code, "name": sf.name, "date": df.date.iloc[-1].strftime("%Y-%m-%d"), "close": float(df.raw_close.iloc[-1]),
           "change": float(df.close.iloc[-1] / df.close.iloc[-2] - 1) if len(df) > 1 else None,
           "horizon": HORIZON, "prob": None, "base_prob": None, "similar_n": None, "note": None}
    try:
        a = analyze(sf, HORIZON)
        row |= {"prob": a["similar"]["up_prob"], "base_prob": a["all"]["up_prob"], "similar_n": a["similar"]["n"]}
    except (NotEnoughHistory, ValueError) as exc:
        row["note"] = str(exc)
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = row
    return row


def _view(request: Request, user: User) -> dict:
    codes = request.app.state.watchlist.codes(user.id)
    try:
        snap = request.app.state.market.snapshot()
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    items = []
    for code in codes:
        try:
            items.append(_row(snap, code))
        except KeyError:
            items.append({"code": code, "name": code, "date": None, "close": None, "change": None, "horizon": HORIZON,
                          "prob": None, "base_prob": None, "similar_n": None, "note": "当前数据里没有这只股票"})
    return {"items": items, "horizon": HORIZON, "data_end": snap.data_end, "data_version": snap.version_id}


@router.get("")
def get_watchlist(request: Request, user: User = Depends(current_user)):
    return _view(request, user)


_hits_cache: dict[str, dict] = {}   # 方法任务 id → 今日符合的股票（任务结果不变，按 id 缓存）


def _selected(jobs, jid: str) -> dict:
    if jid not in _hits_cache:
        r = jobs.result(jid)
        _hits_cache[jid] = {x["code"]: x for x in r["selected"]}
        if len(_hits_cache) > 64:
            _hits_cache.pop(next(iter(_hits_cache)))
    return _hits_cache[jid]


def _pick_row(summary: list[dict], horizon: int = 20) -> dict | None:
    """方法的历史表现取 20 日那一行（没有就取最接近的）。"""
    rows = [r for r in summary if r.get("valid")]
    return min(rows, key=lambda r: abs(r["horizon"] - horizon)) if rows else None


@router.get("/signals")
def signals(request: Request, user: User = Depends(current_user)):
    """自选 × 方法库：你的自选里，今天有哪只符合哪种方法，以及这个方法过去出现之后大多怎么样。"""
    from .patterns import methods as list_methods   # 方法库由系统统一计算；没算过会在这里排队

    codes = request.app.state.watchlist.codes(user.id)
    listed = list_methods(request)["methods"]
    jobs = request.app.state.jobs
    by_code: dict[str, list[dict]] = {c: [] for c in codes}
    names: dict[str, str] = {}
    ready = 0
    for m in listed:
        if m["status"] != "completed":
            continue
        ready += 1
        hits = _selected(jobs, m["job"])
        for code in codes:
            if code in hits:
                x = hits[code]
                names[code] = x["name"]
                by_code[code].append({"index": m["index"], "method": m["name"], "description": m["description"], "job": m["job"],
                                      "date": x["date"], "price": x["price"], "change": x["change"], "reasons": x["reasons"],
                                      "history": _pick_row(m.get("summary") or []), "events": m.get("events")})
    items = [{"code": c, "name": names[c], "hits": h} for c, h in by_code.items() if h]
    data_end = next((m.get("data_end") for m in listed if m.get("data_end")), None)
    return {"items": items, "quiet": [c for c, h in by_code.items() if not h], "watch_count": len(codes),
            "methods_total": len(listed), "methods_ready": ready, "data_end": data_end}


@router.post("/{code}")
def add(request: Request, code: str, user: User = Depends(current_user)):
    code = code.lower()
    try:
        if code not in request.app.state.market.snapshot().row_groups:
            raise HTTPException(404, f"未找到 {code}")
        request.app.state.watchlist.add(user.id, code)
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    except WatchlistFull as exc:
        raise HTTPException(422, str(exc)) from exc
    return _view(request, user)


@router.post("/{code}/remove")
def remove(request: Request, code: str, user: User = Depends(current_user)):
    request.app.state.watchlist.remove(user.id, code.lower())
    return _view(request, user)
