"""行情接口：数据版本、证券搜索、日线、指数。"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from ...data.store import MarketStore, NoDataVersion, UnknownSecurity

router = APIRouter(prefix="/api", tags=["market"])


def _store(request: Request) -> MarketStore:
    return request.app.state.market


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NoDataVersion as exc:
        raise HTTPException(503, str(exc)) from exc
    except UnknownSecurity as exc:
        raise HTTPException(404, f"未找到 {exc.args[0]}") from exc


@router.get("/data/version")
def data_version(request: Request):
    return _guard(_store(request).version)


@router.get("/data/sync-status")
def sync_status(request: Request):
    """最近一次行情同步的结果（只读；手动触发等管理操作在登录完成后提供）。"""
    from ...data.scheduler import read_status
    return read_status(request.app.state.settings.market_dir)


@router.get("/securities")
def search_securities(request: Request, q: str = "", limit: int = Query(20, ge=1, le=100)):
    return _guard(_store(request).search, q, limit)


@router.get("/securities/{code}")
def security(request: Request, code: str):
    return _guard(_store(request).security, code)


@router.get("/securities/{code}/daily")
def security_daily(request: Request, code: str, start: dt.date | None = None, end: dt.date | None = None,
                   adjust: Literal["none", "qfq", "hfq"] = "qfq", limit: int | None = Query(None, ge=1, le=10000)):
    return _guard(_store(request).daily, code, start, end, adjust, limit)


@router.get("/indices")
def indices(request: Request):
    return _guard(_store(request).indices)


@router.get("/indices/{code}/daily")
def index_daily(request: Request, code: str, limit: int | None = Query(250, ge=1, le=10000)):
    return _guard(_store(request).index_daily, code, limit)


@router.get("/securities/{code}/financials")
def security_financials(request: Request, code: str, asof: dt.date | None = None):
    """截止日前已披露的财务报告（按披露时点，不含之后的修订）、TTM 归母净利润与估值。"""
    return _guard(_store(request).financials, code, asof.isoformat() if asof else None)
