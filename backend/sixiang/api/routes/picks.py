"""选股名单：有哪些策略、某一天的名单、历史表现。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Request

from ...data import mcp
from ...data.store import NoDataVersion
from ...picks.service import STRATEGIES

router = APIRouter(prefix="/api/picks", tags=["picks"])


def _known(strategy: str) -> None:
    if strategy not in STRATEGIES:
        raise HTTPException(404, "没有这个选股策略")


@router.get("")
def strategies(request: Request):
    try:
        return {"items": request.app.state.picks.strategies()}
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/stock/{code}")
def of_stock(request: Request, code: str):
    """这只股票在不在最近一次名单里。"""
    return {"pick": request.app.state.picks.of_stock(code.lower())}


def _date(date: str | None) -> None:
    if date:
        try:
            dt.date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(422, "日期格式不对") from exc


@router.get("/{strategy}/report")
def report(request: Request, strategy: str, date: str | None = None):
    """某一天的战报：首页看板和分享图用的那几句话和几个数。"""
    _known(strategy)
    _date(date)
    try:
        return request.app.state.picks.report(strategy, date)
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/{strategy}")
def day(request: Request, strategy: str, date: str | None = None):
    _known(strategy)
    _date(date)
    try:
        return _with_live(request.app.state.picks.day(strategy, date))
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc


def _with_live(day: dict) -> dict:
    """今天的名单在收盘行情同步进来之前，结果是空的：这段时间挂上实时行情（现价、涨幅、此刻是不是封着板）。
    实时行情取不到就不挂，页面照旧显示“等收盘”。"""
    if not day["items"] or day["settled"] or not day["is_today"]:
        return day
    try:
        quotes = mcp.quotes([i["code"] for i in day["items"]])
    except Exception:  # noqa: BLE001
        return day
    for i in day["items"]:
        q = quotes.get(i["code"])
        if q:
            limit = i.get("limit_price")
            i["live"] = {"latest": q["latest"], "change": q["change"], "time": q["time"],
                         "sealed": bool(limit and q["latest"] >= limit - 0.001), "touched": bool(limit and q.get("high") and q["high"] >= limit - 0.001)}
    times = [i["live"]["time"] for i in day["items"] if i.get("live") and i["live"]["time"]]
    day["live_time"] = max(times) if times else None
    return day


@router.get("/{strategy}/stats")
def summary(request: Request, strategy: str):
    _known(strategy)
    try:
        return request.app.state.picks.summary(strategy)
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
