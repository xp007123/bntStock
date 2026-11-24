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
