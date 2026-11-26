"""选股名单：有哪些策略、某一天的名单、历史表现。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Request

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


@router.get("/{strategy}")
def day(request: Request, strategy: str, date: str | None = None):
    _known(strategy)
    if date:
        try:
            dt.date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(422, "日期格式不对") from exc
    try:
        return request.app.state.picks.day(strategy, date)
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/{strategy}/stats")
def summary(request: Request, strategy: str):
    _known(strategy)
    try:
        return request.app.state.picks.summary(strategy)
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
